import markdown
from django.utils import timezone

from django.views.generic import View
from django.shortcuts import render
from django.contrib.auth.mixins import LoginRequiredMixin
from interp.models import User, Task, Translation, ContentVersion, VersionParticle
from django.http import HttpResponse, HttpResponseForbidden, HttpResponseBadRequest

from wkhtmltopdf.views import PDFTemplateView

class Home(LoginRequiredMixin,View):
    def get(self, request, *args, **kwargs):
        user = User.objects.get(username=request.user.username)
        tasks = Task.objects.filter(is_published=True).values_list('id', 'title')
        return render(request, 'questions.html', context={'tasks': tasks, 'language': user.credentials()})


class Questions(LoginRequiredMixin,View):
    def get(self,request,id):
        user = User.objects.get(username=request.user)
        task = Task.objects.get(id=id)
        task_text = task.get_latest_text()
        try:
            trans = Translation.objects.get(user=user, task=task)
        except:
            trans = Translation.objects.create(user=user, task=task, language=user.language)
            trans.add_version(task_text)

        return render(request, 'editor.html',
                      context={'trans': trans.get_latest_text(), 'task': task_text, 'rtl': user.language.rtl, 'quesId': id,
                               'language': str(user.language.name + '-' + user.country.name)})


class SaveQuestion(LoginRequiredMixin,View):
    def post(self,request):
        id = request.POST['id']
        content = request.POST['content']
        task = Task.objects.get(id=id)
        user = User.objects.get(username=request.user)
        translation = Translation.objects.get(user=user,task=task)
        if user != translation.user:
            return HttpResponseForbidden()
        translation.add_version(content)
        VersionParticle.objects.filter(translation=translation).delete()
        return HttpResponse("done")


class Versions(LoginRequiredMixin,View):
    def get(self,request,id):
        user = User.objects.get(username=request.user)
        task = Task.objects.get(id=id)
        try:
            trans = Translation.objects.get(user=user,task=task)
        except:
            trans = Translation.objects.create(user=user, task=task, language=user.language, )

        v = []
        vp = []
        versions = trans.versions.all()
        version_particles = VersionParticle.objects.filter(translation=trans).order_by('date_time')
        for item in version_particles:
            vp.append((item.id,item.date_time))
        for item in versions:
            v.append((item.id,item.create_time))

        return render(request,'versions.html', context={'versions' : v , 'versionParticles':vp ,'translation' : trans.get_latest_text(), 'quesId':trans.id})


class GetVersion(LoginRequiredMixin,View):
    def get(self,request):
        id = request.GET['id']
        version = ContentVersion.objects.get(id=id)
        user = User.objects.get(username=request.user.username)
        if version.content_type.model != 'translation' or version.content_object.user != user:
            return HttpResponseBadRequest()
        return HttpResponse(version.text)


class GetVersionParticle(LoginRequiredMixin,View):
    def get(self,request):
        id = request.GET['id']
        version_particle = VersionParticle.objects.get(id=id)
        user = User.objects.get(username=request.user.username)
        if version_particle.translation.user != user:
            return HttpResponseForbidden()
        return HttpResponse(version_particle.text)


class SaveVersionParticle(LoginRequiredMixin,View):
    def post(self,request):
        id = request.POST['id']
        content = request.POST['content']
        task = Task.objects.get(id=id)
        user = User.objects.get(username=request.user.username)
        translation = Translation.objects.get(user=user, task=task)
        if user != translation.user:
            return HttpResponseForbidden()
        if translation.get_latest_text().strip() == content.strip():
            return HttpResponse("Not Modified")
        last_version_particle = translation.versionparticle_set.order_by('-date_time').first()
        if last_version_particle:
            last_version_particle.text = content
            last_version_particle.save()
        else:
            last_version_particle = VersionParticle.objects.create(translation=translation, text=content, date_time=timezone.now())
        return HttpResponse("done")

class GetTranslatePreview(LoginRequiredMixin,View):
    def get(self,request):
        task_id = self.request.GET['id']
        task = Task.objects.get(id=task_id)
        user = User.objects.get(username=request.user.username)
        translation = Translation.objects.get(user=user, task=task)
        # TODO check if it's available
        direction = 'rtl' if translation.language.rtl else 'ltr'
        return render(request, 'pdf_template.html', context={'content': translation.get_latest_text(),\
                    'direction': direction, 'title': "%s-%s" % (task.title, translation.language)})


class GetTranslatePDF(LoginRequiredMixin, PDFTemplateView):
    filename = 'my_pdf.pdf'
    template_name = 'pdf_template.html'
    cmd_options = {
        'page-size': 'Letter',
        'margin-top': '0.75in',
        'margin-right': '0.75in',
        'margin-bottom': '0.75in',
        'margin-left': '0.75in',
        'zoom': 15,
        'javascript-delay': 500,
    }

    def get_context_data(self, **kwargs):
        context = super(GetTranslatePDF, self).get_context_data(**kwargs)
        task_id = self.request.GET['id']

        user = User.objects.get(username=self.request.user.username)
        task = Task.objects.filter(id=task_id).first()
        if task is None:
            # TODO
            return None

        trans = Translation.objects.get(user=user, task=task)
        if trans is None:
            # TODO
            return None

        self.filename = "%s-%s" % (task.title, trans.language)
        content = trans.get_latest_text()
        context['direction'] = 'rtl' if trans.language.rtl else 'ltr'
        context['content'] = content
        context['title'] = self.filename
        return context