=============================
django-fallback-storage
=============================

..
    .. image:: https://badge.fury.io/py/django-fallback-storage.png
        :target: https://badge.fury.io/py/django-fallback-storage

.. image:: https://travis-ci.org/Draft2Digital/django-fallback-storage.png?branch=master
    :target: https://travis-ci.org/Draft2Digital/django-fallback-storage

``django-fallback-storage`` allows for the use of multiple storage engines at
the same time.  It works by iterating through the declared storage backends
until one succeeds with the desired storage action.

While usable in a production environment, this tool was primarily designed to
help with development of a project.  

Consider a production site using the ``S3BotoStorage`` backend to store its
static assets on Amazon S3 and a development environment that regularly gets
database dumps from the production environment.  In order to get the media
associated with the database dump to work, the development environment could be
configured to use the same S3 bucket.  This could be problematic, as it would
risk making unwanted modifications to the production media.

The ``FallbackStorage`` backend provided by ``django-fallback-storage`` allows
use of the same production production media source in the development
environment while delegating all write operations to a different storage
backend (such as the filesystem).

This is accomplished by wrapping multiple storage backends, and iterating
through them for each request until one of them returns a successful response.


Installation
------------

1. Install the package:

   .. code-block:: bash

       $ pip install django-fallback-storage

2. Set ``fallback_storage.storage.FallbackStorage`` as your desired storage
   backend:

   .. code-block:: python

       # settings.py
       DEFAULT_FILE_STORAGE = "fallback_storage.storage.FallbackStorage"

3. Declare what storage backends fallback storage should use:

   .. code-block:: python

      # All operations will be tried first on `FileSystemStorage`
      # and then on `S3BotoStorage`.
      FALLBACK_STORAGES = (
          "django.core.files.storage.FileSystemStorage",
          "storages.backends.s3boto.S3BotoStorage",
      )

4. Optionally, you can set:

   .. code-block:: python

       # settings.py
       FALLBACK_DATA_MIGRATION = True

   This will put FallbackStorage into a **Data Migration** mode, where it
   will copy accessed files to the first entry in ``FALLBACK_STORAGES``
   that can store them.

   A scenario where this might be useful would be if you changed data centers,
   and your system's access to your new data center's storage is much faster than
   accessing your old data center's storage, but you have not yet moved all data
   over to the new data center. Any data that is being accessed by your users will
   be migrated to the new data center upon access, and you can have a process that
   is going through moving all of the rest of the data while you are still serving
   your users.

API
---

``FallbackStorage`` implements all of the following backend methods.

* ``_open()``
* ``_save()``
* ``delete()``
* ``exists()``
* ``listdir()``
* ``size()``
* ``url()``
* ``accessed_time()``
* ``created_time()``
* ``modified_time()``
* ``get_valid_name()``
* ``get_available_name()``
* ``path()``

When one of these methods is called, each backend declared in
``FALLBACK_STORAGES`` is called.  The first successful response is
returned.

Any backend which does not implement a given method will be skipped over.  If
none of the backends implement a called method, then an ``AttributeError`` is
raised.

Exceptions raised by any backend are reraised if none of the backends returns a
successful response.

The following methods behave somewhat specially.

* **FallbackStorage.exists(name)**:

  Will return ``True`` if the file exists in *any* of the storage backends.

* **FallbackStorage.listdir(path)**:

  Will return the set of all directories and files in all of the storage backends.

* **FallbackStorage.url(name)**:

  If you **have not** set ``FALLBACK_DATA_MIGRATION`` to be ``True``, then
  when computing a url, FallbackStorage first checks if the file exists.  If
  the file exists in none of the storage backends, the last backend is used to
  compute the file name.

  If you **do have** ``FALLBACK_DATA_MIGRATION`` set to ``True``, then the
  returned url will be the first successful response from the defined ``FALLBACK_STORAGES``.

* **FallbackStorage.open(name, mode='rb')**:

  FallbackStorage will return the first successful response from the
  defined ``FALLBACK_STORAGES``.

  If you have ``FALLBACK_DATA_MIGRATION`` set to ``True``, then
  it will first call **FallbackStorage.save()** on the content of
  the file to save it to the first ``FALLBACK_STORAGES`` entry
  that will accept it.
