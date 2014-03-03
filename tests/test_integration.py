# coding: utf-8

from __future__ import absolute_import, unicode_literals

import os
from xml.etree import ElementTree as ET

try:
    from selenium import webdriver
    from selenium.common.exceptions import NoSuchElementException
    from selenium.webdriver.support.wait import WebDriverWait
except ImportError:
    webdriver = None

from django.test import LiveServerTestCase, RequestFactory, TestCase
from django.test.utils import override_settings
from django.utils.unittest import skipIf, skipUnless

from debug_toolbar.middleware import DebugToolbarMiddleware, show_toolbar

from .base import BaseTestCase
from .views import regular_view, streaming_view, json_view


rf = RequestFactory()


@override_settings(DEBUG=True)
class DebugToolbarTestCase(BaseTestCase):

    def test_show_toolbar(self):
        self.assertTrue(show_toolbar(self.request))

    def test_show_toolbar_DEBUG(self):
        with self.settings(DEBUG=False):
            self.assertFalse(show_toolbar(self.request))

    def test_show_toolbar_INTERNAL_IPS(self):
        with self.settings(INTERNAL_IPS=[]):
            self.assertFalse(show_toolbar(self.request))

    def _resolve_stats(self, path):
        # takes stats from Request panel
        self.request.path = path
        panel = self.toolbar.get_panel_by_id('RequestPanel')
        panel.process_request(self.request)
        panel.process_response(self.request, self.response)
        return panel.get_stats()

    def test_url_resolving_positional(self):
        stats = self._resolve_stats('/resolving1/a/b/')
        self.assertEqual(stats['view_urlname'], 'positional-resolving')
        self.assertEqual(stats['view_func'], 'tests.views.resolving_view')
        self.assertEqual(stats['view_args'], ('a', 'b'))
        self.assertEqual(stats['view_kwargs'], {})

    def test_url_resolving_named(self):
        stats = self._resolve_stats('/resolving2/a/b/')
        self.assertEqual(stats['view_args'], ())
        self.assertEqual(stats['view_kwargs'], {'arg1': 'a', 'arg2': 'b'})

    def test_url_resolving_mixed(self):
        stats = self._resolve_stats('/resolving3/a/')
        self.assertEqual(stats['view_args'], ('a',))
        self.assertEqual(stats['view_kwargs'], {'arg2': 'default'})

    def test_url_resolving_bad(self):
        stats = self._resolve_stats('/non-existing-url/')
        self.assertEqual(stats['view_urlname'], 'None')
        self.assertEqual(stats['view_args'], 'None')
        self.assertEqual(stats['view_kwargs'], 'None')
        self.assertEqual(stats['view_func'], '<no view>')

    # Django doesn't guarantee that process_request, process_view and
    # process_response always get called in this order.

    def test_middleware_view_only(self):
        DebugToolbarMiddleware().process_view(self.request, regular_view, ('title',), {})

    def test_middleware_response_only(self):
        DebugToolbarMiddleware().process_response(self.request, self.response)

    def test_middleware_response_insertion__regular_view(self):
        resp = regular_view(self.request, "İ")
        DebugToolbarMiddleware().process_response(self.request, resp)
        # check toolbar insertion before "</body>"
        self.assertContains(resp, '</div>\n</body>')

    def test_middleware_response_insertion__streaming_view__header_off(self):
        DebugToolbarMiddleware().process_request(self.request)
        
        resp = streaming_view(self.request, "İ")
        
        DebugToolbarMiddleware().process_response(self.request, resp)
        # check toolbar insertion before "</body>"
        
        content = u''.join([s.decode('utf-8') for s in resp.streaming_content])
        
        self.assertNotIn('</div>\n</body>', content)
        
        self.assertNotIn(DebugToolbarMiddleware.HEADER_NAME, resp)

    @override_settings(DEBUG_TOOLBAR_CONFIG={'DEBUG_URI_HEADER': True})
    def test_middleware_response_insertion__streaming_view__header_on(self):
        DebugToolbarMiddleware().process_request(self.request)
        
        resp = streaming_view(self.request, "İ")
        
        DebugToolbarMiddleware().process_response(self.request, resp)
        # check toolbar insertion before "</body>"
        
        content = u''.join([s.decode('utf-8') for s in resp.streaming_content])
        
        self.assertNotIn('</div>\n</body>', content)
        
        uri = resp[DebugToolbarMiddleware.HEADER_NAME]
        
        self.assertRegexpMatches(uri, r'^/media/debug-toolbar/[\w-]{36}\.html$')
        
        file_name = uri[7:]
        
        storage = DebugToolbarMiddleware.get_storage()
        
        f = storage.open(file_name)
        
        toolbar_markup_page = f.read()
        
        self.assertNotIn('<textarea>'+content+'</textarea>', toolbar_markup_page)
        self.assertIn('</div>\n</body>', toolbar_markup_page)
        
        storage.delete(file_name)

    def test_middleware_response_insertion__json_view__header_off(self):
        DebugToolbarMiddleware().process_request(self.request)
        
        resp = json_view(self.request)
        
        DebugToolbarMiddleware().process_response(self.request, resp)
        # check toolbar insertion before "</body>"
        self.assertNotContains(resp, '</div>\n</body>')
        self.assertNotIn(DebugToolbarMiddleware.HEADER_NAME, resp)

    @override_settings(DEBUG_TOOLBAR_CONFIG={'DEBUG_URI_HEADER': True})
    def test_middleware_response_insertion__json_view__header_on__no_ajax(self):
        self.assertFalse(self.request.is_ajax())
        
        DebugToolbarMiddleware().process_request(self.request)
        
        resp = json_view(self.request)
        
        DebugToolbarMiddleware().process_response(self.request, resp)
        
        # check toolbar insertion before "</body>"
        self.assertNotContains(resp, '</div>\n</body>')
        
        uri = resp[DebugToolbarMiddleware.HEADER_NAME]
        
        self.assertRegexpMatches(uri, r'^/media/debug-toolbar/[\w-]{36}\.html$')
        
        file_name = uri[7:]
        
        storage = DebugToolbarMiddleware.get_storage()
        
        f = storage.open(file_name)
        
        toolbar_markup_page = f.read()
        
        self.assertIn('<textarea>'+resp.content+'</textarea>', toolbar_markup_page)
        self.assertIn('</div>\n</body>', toolbar_markup_page)
        
        storage.delete(file_name)
    
    @override_settings(DEBUG_TOOLBAR_CONFIG={'DEBUG_URI_HEADER': True})
    def test_middleware_response_insertion__json_view__header_on__with_ajax(self):
        self.request.META['HTTP_X_REQUESTED_WITH'] = 'XMLHttpRequest'
        
        self.assertTrue(self.request.is_ajax())
        
        DebugToolbarMiddleware().process_request(self.request)
        
        resp = json_view(self.request)
        
        DebugToolbarMiddleware().process_response(self.request, resp)
        
        # check toolbar insertion before "</body>"
        self.assertNotContains(resp, '</div>\n</body>')
        
        uri = resp[DebugToolbarMiddleware.HEADER_NAME]
        
        self.assertRegexpMatches(uri, r'^/media/debug-toolbar/[\w-]{36}\.html$')
        
        file_name = uri[7:]
        
        storage = DebugToolbarMiddleware.get_storage()
        
        f = storage.open(file_name)
        
        toolbar_markup_page = f.read()
        
        self.assertIn('<textarea>'+resp.content+'</textarea>', toolbar_markup_page)
        self.assertIn('</div>\n</body>', toolbar_markup_page)
        
        storage.delete(file_name)


@override_settings(DEBUG=True)
class DebugToolbarIntegrationTestCase(TestCase):

    def test_middleware(self):
        response = self.client.get('/execute_sql/')
        self.assertEqual(response.status_code, 200)

    @override_settings(DEFAULT_CHARSET='iso-8859-1')
    def test_non_utf8_charset(self):
        response = self.client.get('/regular/ASCII/')
        self.assertContains(response, 'ASCII')      # template
        self.assertContains(response, 'djDebug')    # toolbar

        response = self.client.get('/regular/LÀTÍN/')
        self.assertContains(response, 'LÀTÍN')      # template
        self.assertContains(response, 'djDebug')    # toolbar

    def test_xml_validation(self):
        response = self.client.get('/regular/XML/')
        ET.fromstring(response.content)     # shouldn't raise ParseError


@skipIf(webdriver is None, "selenium isn't installed")
@skipUnless('DJANGO_SELENIUM_TESTS' in os.environ, "selenium tests not requested")
@override_settings(DEBUG=True)
class DebugToolbarLiveTestCase(LiveServerTestCase):

    @classmethod
    def setUpClass(cls):
        super(DebugToolbarLiveTestCase, cls).setUpClass()
        cls.selenium = webdriver.Firefox()

    @classmethod
    def tearDownClass(cls):
        cls.selenium.quit()
        super(DebugToolbarLiveTestCase, cls).tearDownClass()

    def test_basic(self):
        self.selenium.get(self.live_server_url + '/regular/basic/')
        version_panel = self.selenium.find_element_by_id('VersionsPanel')

        # Versions panel isn't loaded
        with self.assertRaises(NoSuchElementException):
            version_panel.find_element_by_tag_name('table')

        # Click to show the versions panel
        self.selenium.find_element_by_class_name('VersionsPanel').click()

        # Version panel loads
        table = WebDriverWait(self.selenium, timeout=10).until(
            lambda selenium: version_panel.find_element_by_tag_name('table'))
        self.assertIn("Name", table.text)
        self.assertIn("Version", table.text)

    @override_settings(DEBUG_TOOLBAR_CONFIG={'RESULTS_STORE_SIZE': 0})
    def test_expired_store(self):
        self.selenium.get(self.live_server_url + '/regular/basic/')
        version_panel = self.selenium.find_element_by_id('VersionsPanel')

        # Click to show the version panel
        self.selenium.find_element_by_class_name('VersionsPanel').click()

        # Version panel doesn't loads
        error = WebDriverWait(self.selenium, timeout=10).until(
            lambda selenium: version_panel.find_element_by_tag_name('p'))
        self.assertIn("Data for this panel isn't available anymore.", error.text)
