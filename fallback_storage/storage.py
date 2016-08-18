import logging
from io import BytesIO
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.files.base import ContentFile
from django.core.files.storage import (
    Storage,
    get_storage_class,
)


logger = logging.getLogger(__name__)

def concatenate_exceptions(exceptions):
    return '\n'.join((
        "{0}: {1}".format(b, e) for e, b in exceptions.items()
    ))


def fallback_method(method_name):
    """
    Returns a method that will return the first successful response from a
    storage backend.
    """
    def method(self, *args, **kwargs):
        exceptions = {}

        for backend_class, backend_method in self.get_backend_methods(method_name):
            try:
                return backend_method(*args, **kwargs)
            except Exception as e:
                exceptions[backend_class] = e
                continue

        if exceptions:
            if len(exceptions) == 1:
                raise exceptions[0]
            raise Exception(concatenate_exceptions(exceptions))
        else:
            raise AttributeError(
                "No backend has the method `{0}`".format(method_name),
            )
    method.__name__ = method_name
    return method


class FallbackStorage(Storage):
    def __init__(self, backends=None):
        if backends is None:
            try:
                assert settings.FALLBACK_STORAGES
                backends = settings.FALLBACK_STORAGES
            except (AttributeError, AssertionError):
                raise ImproperlyConfigured("The setting `FALLBACK_STORAGES` is "
                                           "either missing or empty")
        self.backend_classes = backends
        self.in_data_migration = getattr(settings, "FALLBACK_DATA_MIGRATION", False)

    def get_backends(self):
        for backend_class in self.backend_classes:
            backend = get_storage_class(backend_class)()
            yield backend_class, backend

    def get_primary_backend(self):
        backend_class, backend = next(self.get_backends())
        return backend

    def get_backend_methods(self, method_name):
        for backend_class, backend in self.get_backends():
            if hasattr(backend, method_name):
                yield backend_class, getattr(backend, method_name)

    # Primary Methods
    _open = fallback_method('_open')
    _save = fallback_method('_save')

    # Optional Methods
    delete = fallback_method('delete')
    size = fallback_method('size')
    accessed_time = fallback_method('accessed_time')
    created_time = fallback_method('created_time')
    modified_time = fallback_method('modified_time')

    # Public API Methods
    get_valid_name = fallback_method('get_valid_name')
    get_available_name = fallback_method('get_available_name')
    path = fallback_method('path')

    def exists(self, *args, **kwargs):
        exceptions = {}

        for backend_class, backend_method in self.get_backend_methods('exists'):
            try:
                result = backend_method(*args, **kwargs)
                if result:
                    return True
            except Exception as e:
                exceptions[backend_class] = e
                continue

        if exceptions:
            if len(exceptions) == 1:
                raise exceptions[0]
            raise Exception(concatenate_exceptions(exceptions))
        else:
            return False

    def listdir(self, *args, **kwargs):
        exceptions = {}
        directories = []
        files = []

        for backend_class, backend_method in self.get_backend_methods('listdir'):
            try:
                dirs, files_ = backend_method(*args, **kwargs)
                directories.extend(dirs)
                files.extend(files_)
            except Exception as e:
                exceptions[backend_class] = e
                continue

        if (any(directories) or any(files)) or not exceptions:
            return directories, files
        elif exceptions:
            if len(exceptions) == 1:
                raise exceptions[0]
            raise Exception(concatenate_exceptions(exceptions))
        else:
            raise AttributeError("No backend found with the method `listdir`")

    def url(self, name):
        if self.in_data_migration:
            return fallback_method("url")(self, name)
        else:
            exceptions = {}

            for backend_class, backend in self.get_backends():
                if not hasattr(backend, 'url') or not hasattr(backend, 'exists'):
                    continue

                if not backend.exists(name):
                    continue
                try:
                    return backend.url(name)
                except Exception as e:
                    exceptions[backend_class] = e
                    continue
            if exceptions:
                if len(exceptions) == 1:
                    raise exceptions[0]
                raise Exception(concatenate_exceptions(exceptions))
            else:
                last_backend = get_storage_class(self.backend_classes[-1])()
                try:
                    return last_backend.url(name)
                except AttributeError:
                    raise AttributeError("No backend found with the method `url`")

    def open(self, name, mode='rb'):
        if self.in_data_migration:
            exceptions = {}
            result = None

            for i, (backend_class, backend_method) in enumerate(self.get_backend_methods('open')):
                try:
                    result = backend_method(name, mode=mode)
                    if result:
                        if self.in_data_migration and i > 0:
                            # We have a file that isn't in the primary backend, but
                            # some other backend.
                            if mode in ['rb', 'br']:
                                content = result.read()
                                result = ContentFile(content, name=name)
                                # Save the file to move it into the primary backend
                                self.__save_to_primary_backend(name, BytesIO(content))
                            else:
                                # Fetch the data a second time since the mode
                                # isn't 'rb', and I'm not sure the returned
                                # file is re-entrant.
                                try:
                                    second_result = backend_method(name)
                                    if second_result:
                                        self.__save_to_primary_backend(name, second_result)
                                except Exception as e:
                                    logger.exception(("Unable to save file into the "
                                                      "primary backend when fetched from other backend. "
                                                      "Mode='{mode}', name='{name}'").format(mode=mode, name=name))
                        return result
                except Exception as e:
                    exceptions[backend_class] = e
                    continue

            if exceptions:
                if len(exceptions) == 1:
                    raise exceptions[0]
                raise Exception(concatenate_exceptions(exceptions))
            else:
                return result
        else:
            return fallback_method("open")(self, name, mode=mode)

    def __save_to_primary_backend(self, name, file_obj):
        # (str, django.core.files.base.File) -> Optional[str]
        """
        Copy the file to the primary backend for future retrievals and return the name.
        If this isn't able to do so, it will log the exception and return None.
        """
        try:
            backend = self.get_primary_backend()
            return backend.save(name, file_obj)
        except Exception as e:
            message = "Unable to save file into the primary backend when fetched from other backend. Name='{name}'"
            logger.exception(message.format(name=name))
