# coding: utf-8

from __future__ import absolute_import, unicode_literals

import json

from django.contrib.auth.models import User
from django.http import HttpResponse, StreamingHttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string


def execute_sql(request):
    list(User.objects.all())
    return HttpResponse()


def regular_view(request, title):
    return render(request, 'basic.html', {'title': title})


def streaming_view(request, title):
    content = render_to_string('basic.html', {'title': title})
    
    return StreamingHttpResponse(iter([content[:11], content[11:]]))

def json_view(request):
    content = json.dumps({'objects': [{'id': u.id} for u in User.objects.all()]})
    
    return HttpResponse(content, content_type='application/json')


def new_user(request, username='joe'):
    User.objects.create_user(username=username)
    return render(request, 'basic.html', {'title': 'new user'})


def resolving_view(request, arg1, arg2):
    # see test_url_resolving in tests.py
    return HttpResponse()
