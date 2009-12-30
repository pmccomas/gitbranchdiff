from django.conf.urls.defaults import *
from views import *

# Uncomment the next two lines to enable the admin:
# from django.contrib import admin
# admin.autodiscover()

urlpatterns = patterns('',
    # Example:
	(r'^$', matrix),
	(r'^diff/$', diff),
)
