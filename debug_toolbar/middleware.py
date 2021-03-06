"""
Debug Toolbar middleware
"""

from __future__ import absolute_import, unicode_literals

import re
import threading
import uuid

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import get_storage_class
from django.utils.encoding import force_text
from django.utils.importlib import import_module

from debug_toolbar.toolbar import DebugToolbar
from debug_toolbar import settings as dt_settings

_HTML_TYPES = ('text/html', 'application/xhtml+xml')
# Handles python threading module bug - http://bugs.python.org/issue14308
threading._DummyThread._Thread__stop = lambda x: 1


def show_toolbar(request):
    """
    Default function to determine whether to show the toolbar on a given page.
    """
    if request.META.get('REMOTE_ADDR', None) not in settings.INTERNAL_IPS:
        return False

    if request.is_ajax() and not dt_settings.CONFIG['DEBUG_URI_HEADER']:
        return False

    return bool(settings.DEBUG)


class DebugToolbarMiddleware(object):
    """
    Middleware to set up Debug Toolbar on incoming request and render toolbar
    on outgoing response.
    """
    HEADER_NAME = 'X-DEBUG-URI'
    debug_toolbars = {}

    @classmethod
    def get_current_toolbar(cls, method='get'):
        return getattr(cls.debug_toolbars, method)(threading.current_thread().ident, None)

    @classmethod
    def set_current_toolbar(cls, toolbar):
        cls.debug_toolbars[threading.current_thread().ident] = toolbar

    @classmethod
    def get_storage(cls, toolbar=None):
        if toolbar:
            storage_name = toolbar.config['DEBUG_URI_STORAGE']
        else:
            storage_name = dt_settings.CONFIG['DEBUG_URI_STORAGE']
        
        return get_storage_class(storage_name)()

    def store_toolbar(self, response, toolbar):
        html = '<html><body>'
        
        content_encoding = response.get('Content-Encoding', '')
        
        # don't bother trying to display streaming or encoded data
        if not getattr(response, 'streaming', False) and 'gzip' not in content_encoding:
            html += '<textarea>'+response.content+'</textarea>'
        
        html += toolbar.render_toolbar()+'</body></html>'
        
        name = 'debug-toolbar/%s.html' % uuid.uuid1()
        
        storage = self.__class__.get_storage(toolbar=toolbar)
        
        name = storage.save(name, ContentFile(html))
        
        return storage.url(name)

    def process_request(self, request):
        # Decide whether the toolbar is active for this request.
        func_path = dt_settings.CONFIG['SHOW_TOOLBAR_CALLBACK']
        # Replace this with import_by_path in Django >= 1.6.
        mod_path, func_name = func_path.rsplit('.', 1)
        show_toolbar = getattr(import_module(mod_path), func_name)
        if not show_toolbar(request):
            return

        toolbar = DebugToolbar(request)
        self.__class__.set_current_toolbar(toolbar)

        # Activate instrumentation ie. monkey-patch.
        for panel in toolbar.enabled_panels:
            panel.enable_instrumentation()

        # Run process_request methods of panels like Django middleware.
        response = None
        for panel in toolbar.enabled_panels:
            response = panel.process_request(request)
            if response:
                break
        return response

    def process_view(self, request, view_func, view_args, view_kwargs):
        toolbar = self.__class__.get_current_toolbar()
        if not toolbar:
            return

        # Run process_view methods of panels like Django middleware.
        response = None
        for panel in toolbar.enabled_panels:
            response = panel.process_view(request, view_func, view_args, view_kwargs)
            if response:
                break
        return response

    def process_response(self, request, response):
        toolbar = self.__class__.get_current_toolbar(method='pop')
        
        if not toolbar:
            return response

        # Run process_response methods of panels like Django middleware.
        for panel in reversed(toolbar.enabled_panels):
            new_response = panel.process_response(request, response)
            if new_response:
                response = new_response

        # Deactivate instrumentation ie. monkey-unpatch. This must run
        # regardless of the response. Keep 'return' clauses below.
        # (NB: Django's model for middleware doesn't guarantee anything.)
        for panel in reversed(toolbar.enabled_panels):
            panel.disable_instrumentation()

        # Check for responses where the toolbar can't be inserted.
        content_encoding = response.get('Content-Encoding', '')
        content_type = response.get('Content-Type', '').split(';')[0]
        if any((getattr(response, 'streaming', False),
                'gzip' in content_encoding,
                content_type not in _HTML_TYPES)):
            
            if toolbar.config['DEBUG_URI_HEADER']:
                response[self.HEADER_NAME] = self.store_toolbar(response, toolbar)
            
            return response

        # Collapse the toolbar by default if SHOW_COLLAPSED is set.
        if toolbar.config['SHOW_COLLAPSED'] and 'djdt' not in request.COOKIES:
            response.set_cookie('djdt', 'hide', 864000)

        # Insert the toolbar in the response.
        content = force_text(response.content, encoding=settings.DEFAULT_CHARSET)
        insert_before = dt_settings.CONFIG['INSERT_BEFORE']
        try:                    # Python >= 2.7
            pattern = re.escape(insert_before)
            bits = re.split(pattern, content, flags=re.IGNORECASE)
        except TypeError:       # Python < 2.7
            pattern = '(.+?)(%s|$)' % re.escape(insert_before)
            matches = re.findall(pattern, content, flags=re.DOTALL | re.IGNORECASE)
            bits = [m[0] for m in matches if m[1] == insert_before]
            # When the body ends with a newline, there's two trailing groups.
            bits.append(''.join(m[0] for m in matches if m[1] == ''))
        if len(bits) > 1:
            bits[-2] += toolbar.render_toolbar()
            response.content = insert_before.join(bits)
            if response.get('Content-Length', None):
                response['Content-Length'] = len(response.content)
        return response
