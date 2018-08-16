import os
from urllib.parse import urljoin
from uuid import uuid4
import logging
import requests

from django.conf import settings
from django.http import HttpResponse
from django.template.loader import render_to_string

import asyncio
import pyppeteer

logger = logging.getLogger(__name__)

from trans.utils.translation import get_requested_user, \
    get_task_by_contest_and_name, get_trans_by_user_and_task


def get_translation_by_contest_and_task_type(request, user, contest_slug, task_name, task_type):
    requested_user = get_requested_user(request, task_type)
    task = get_task_by_contest_and_name(contest_slug, task_name,
                                        user.is_editor())

    if task_type == 'released':
        return task.get_base_translation()
    return get_trans_by_user_and_task(requested_user, task)


def render_pdf_template(request, user, contest_slug, task_name, task_type,
                        static_path, images_path, pdf_output):
    requested_user = get_requested_user(request, task_type)
    task = get_task_by_contest_and_name(contest_slug, task_name,
                                        user.is_editor())

    if task_type == 'released':
        content = task.get_published_text()
    else:
        trans = get_trans_by_user_and_task(requested_user, task)
        content = trans.get_latest_text()

    context = {
        'content': content,
        'contest': task.contest.title,
        'task_name': task.name,
        'country': requested_user.country.code,
        'language': requested_user.language.name,
        'language_code': requested_user.language.code,
        'direction': requested_user.language.direction(),
        'username': requested_user.username,
        'pdf_output': pdf_output,
        'static_path': static_path,
        'images_path': images_path,
        'text_font_base64': requested_user.text_font_base64
    }
    return render_to_string('pdf-template.html', context=context,
                            request=request)

# pdf file paths (excepting final pdf path)
def output_pdf_path(contest_slug, task_name, task_type, user):
    file_path = '{}/output/{}/{}/{}'.format(settings.MEDIA_ROOT, contest_slug, task_name, task_type)
    file_name = '{}-{}.pdf'.format(task_name, user.username)
    pdf_file_path = '{}/{}'.format(file_path, file_name)
    os.makedirs(file_path, exist_ok=True)
    return pdf_file_path

def released_pdf_path(contest_slug, task_name, user):
    return output_pdf_path(contest_slug, task_name, 'released', user)

def unreleased_pdf_path(contest_slug, task_name, user):
    return output_pdf_path(contest_slug, task_name, 'task', user)

# base pdf is a pdf of ISC
def base_pdf_path(contest_slug, task_name, task_type):
    user = User.objects.get(username='ISC')
    return output_pdf_path(contest_slug, task_name, task_type, user)

def final_pdf_path(contest_slug, task_name, user):
    file_path = '{}/final/pdf/{}/{}'.format(settings.MEDIA_ROOT, contest_slug, task_name)
    file_name = '{}-{}.pdf'.format(task_name, user.username)
    if user.username == 'ISC':
        file_path = '{}/final/pdf/{}'.format(settings.MEDIA_ROOT, contest_slug)
        file_name = '{}.pdf'.format(task_name)
    pdf_file_path = '{}/{}'.format(file_path, file_name)
    os.makedirs(file_path, exist_ok=True)
    return pdf_file_path

def final_markdown_path(contest_slug, task_name, user):
    file_path = '{}/final/markdown/{}/{}'.format(settings.MEDIA_ROOT, contest_slug, task_name)
    file_name = '{}-{}.md'.format(task_name, user.username)
    if user.username == 'ISC':
        file_path = '{}/final/markdown/{}'.format(settings.MEDIA_ROOT, contest_slug)
        file_name = '{}.md'.format(task_name)
    md_file_path = '{}/{}'.format(file_path, file_name)
    os.makedirs(file_path, exist_ok=True)
    return md_file_path


def get_file_name_from_path(file_path):
    return file_path.split('/')[-1]


def pdf_response(pdf_file_path, file_name):
    with open(pdf_file_path, 'rb') as pdf:
        response = HttpResponse(pdf.read(), content_type='application/pdf')
        response['Content-Disposition'] = 'inline;filename={}'.format(file_name)
        response['pdf_file_path'] = pdf_file_path
        return response


async def _convert_html_to_pdf(html_file_path, pdf_file_path):
    browser = await pyppeteer.launch({
        'executablePath': settings.CHROMIUM_EXECUTABLE_PATH,
        'args': ['--no-sandbox'],
    })
    page = await browser.newPage()
    await page.goto('file://{}'.format(html_file_path))
    await page.pdf({'path': pdf_file_path, **settings.CHROMIUM_PDF_OPTIONS})
    await browser.close()

def convert_html_to_pdf(html, pdf_file_path):
    uuid = str(uuid4())
    html_file_path = '/tmp/{}.html'.format(uuid)

    with open(html_file_path, 'wb') as f:
        f.write(html.encode('utf-8'))

    asyncio.get_event_loop().run_until_complete(
        _convert_html_to_pdf(html_file_path, pdf_file_path))
    os.remove(html_file_path)

def add_page_numbers_to_pdf(pdf_file_path, task_name):
    color =  '-color "0.4 0.4 0.4" '
    cmd = ('cpdf -add-text "{0} (%Page of %EndPage)   " -font "Arial" ' + color + \
          '-font-size 10 -bottomright .62in {1} -o {1}').format(task_name.capitalize(), pdf_file_path)
    os.system(cmd)


def add_info_line_to_pdf(pdf_file_path, info):
    color =  '-color "0.4 0.4 0.4" '
    output_pdf_path = '/tmp/{}.pdf'.format(str(uuid4()))
    cmd = 'cpdf -add-text "   {}" -font "Arial" -font-size 10 -bottomleft .62in {} -o {} {}'.format(
        info, pdf_file_path, output_pdf_path, color)
    os.system(cmd)
    return output_pdf_path


def send_pdf_to_printer(pdf_file_path, country_code, country_name, cover_page=False, count=1):
    with open(pdf_file_path, 'rb') as pdf_file:
        response = requests.post(
            urljoin(settings.PRINT_SYSTEM_ADDRESS, '/translation'),
            files={'pdf': pdf_file},
            data={
                'country_code': country_code,
                'country_name': country_name,
                'cover_page': (1 if cover_page else 0),
                'count': count,
            },
        )
    response.raise_for_status()
