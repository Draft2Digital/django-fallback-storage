from __future__ import unicode_literals

import functools
import six

from io import BytesIO

import pytest

from inmemorystorage.storage import (
    InMemoryStorage,
    InMemoryDir,
)

from django.core.files.storage import (
    get_storage_class,
    FileSystemStorage,
)


@pytest.fixture
def inmemorystorage(mocker):
    """
    Makes the InMemoryStorage backend persist its filesystem across multiple
    instantiations.
    """
    filesystem = InMemoryDir()

    MockedInMemoryStorage = functools.partial(
        InMemoryStorage,
        filesystem=filesystem,
        base_url='http://www.example.com/media/',
    )
    mocker.patch(
        'inmemorystorage.storage.InMemoryStorage',
        new=MockedInMemoryStorage,
    )

    return MockedInMemoryStorage()


@pytest.fixture
def filesystemstorage(tmpdir, settings):
    """
    Fixes the file system location of the FileSystemStorage class to default to
    a temporary directory.
    """
    settings.MEDIA_ROOT = tmpdir.strpath
    settings.MEDIA_URL = '/media/'
    return FileSystemStorage()


@pytest.mark.parametrize(
    'storage_backend',
    (
        'inmemorystorage.storage.InMemoryStorage',
        'django.core.files.storage.FileSystemStorage',
    )
)
def test_storage_fixtures(filesystemstorage, inmemorystorage, settings, storage_backend):
    """
    Sanity check that the storage fixtures correctly patch the backends.
    """
    settings.DEFAULT_FILE_STORAGE = storage_backend
    storage_a = get_storage_class()()
    storage_b = get_storage_class()()

    assert not storage_a.exists('foo.txt')
    assert not storage_b.exists('foo.txt')

    storage_a.save('foo.txt', BytesIO(b'test'))

    assert storage_b.exists('foo.txt')
    fb = storage_b.open('foo.txt')
    contents = fb.read()
    if isinstance(contents, six.binary_type):
        contents = six.text_type(contents, encoding='utf8')
    assert 'test' in contents


def test_fallback_for_open_operations(inmemorystorage, filesystemstorage, settings):
    settings.FALLBACK_DATA_MIGRATION = True
    inmemorystorage.save('bar.txt', BytesIO(b'test-bar'))
    filesystemstorage.save('foo.txt', BytesIO(b'test-foo'))

    backend = get_storage_class()()

    assert inmemorystorage.exists('bar.txt')
    assert not inmemorystorage.exists('foo.txt')

    assert filesystemstorage.exists('foo.txt')
    assert not filesystemstorage.exists('bar.txt')

    foo_file = backend.open('foo.txt')
    assert b'test-foo' in foo_file.read()
    bar_file = backend.open('bar.txt')
    assert b'test-bar' in bar_file.read()

    assert inmemorystorage.exists('bar.txt')
    # This is the actual new behavior due to the data-migration flag being turned on
    assert inmemorystorage.exists('foo.txt')

    assert filesystemstorage.exists('foo.txt')
    assert not filesystemstorage.exists('bar.txt')


def test_fallback_for_save_operations(inmemorystorage, filesystemstorage):
    backend = get_storage_class()()
    backend.save('foo.txt', BytesIO(b'test'))

    assert inmemorystorage.exists('foo.txt')
    assert not filesystemstorage.exists('foo.txt')

    f = inmemorystorage.open('foo.txt')
    assert b'test' in f.read()


def test_fallback_for_exists_operations(inmemorystorage, filesystemstorage):
    inmemorystorage.save('bar.txt', BytesIO(b'test-bar'))
    filesystemstorage.save('foo.txt', BytesIO(b'test-foo'))

    backend = get_storage_class()()

    assert backend.exists('foo.txt')
    assert backend.exists('bar.txt')


def test_fallback_for_deletion(inmemorystorage, filesystemstorage):
    inmemorystorage.save('foo.txt', BytesIO(b'test-foo-b'))
    filesystemstorage.save('foo.txt', BytesIO(b'test-foo-a'))

    backend = get_storage_class()()

    # sanity check
    assert inmemorystorage.exists('foo.txt')
    assert filesystemstorage.exists('foo.txt')

    backend.delete('foo.txt')

    assert not inmemorystorage.exists('foo.txt')
    # should still exist in the second backend.
    assert filesystemstorage.exists('foo.txt')
    assert 'test-foo-a' in six.text_type(
        filesystemstorage.open('foo.txt').read(), encoding='utf8',
    )


def test_fallback_for_listdir(inmemorystorage, filesystemstorage):
    inmemorystorage.save('bar.txt', BytesIO(b'test-bar'))
    filesystemstorage.save('foo.txt', BytesIO(b'test-foo'))

    backend = get_storage_class()()

    assert 'foo.txt' in filesystemstorage.listdir('')[1]
    assert 'bar.txt' in inmemorystorage.listdir('')[1]

    assert 'foo.txt' in backend.listdir('')[1]
    assert 'bar.txt' in backend.listdir('')[1]


def test_fallback_for_size(inmemorystorage, filesystemstorage):
    inmemorystorage.save('bar.txt', BytesIO(b'test-0'))
    filesystemstorage.save('foo.txt', BytesIO(b'test-01234'))

    foo_size = filesystemstorage.size('foo.txt')
    bar_size = inmemorystorage.size('bar.txt')

    # this one should not get accessed
    filesystemstorage.save('bar.txt', BytesIO(b'test-0123456789'))

    backend = get_storage_class()()

    assert backend.size('foo.txt') == foo_size
    assert backend.size('bar.txt') == bar_size


def test_fallback_for_url(inmemorystorage, filesystemstorage, settings):
    settings.FALLBACK_DATA_MIGRATION = True
    inmemorystorage.save('bar.txt', BytesIO(b'test-bar'))
    filesystemstorage.save('foo.txt', BytesIO(b'test-foo'))

    # sanity check
    assert inmemorystorage.url('bar.txt') == 'http://www.example.com/media/bar.txt'
    assert filesystemstorage.url('foo.txt') == '/media/foo.txt'

    backend = get_storage_class()()

    assert backend.url('bar.txt') == 'http://www.example.com/media/bar.txt'
    assert backend.url('foo.txt') == 'http://www.example.com/media/foo.txt'

    backend.save('foo.txt', BytesIO(b'test-in-memory-foo'))
    assert backend.url('foo.txt') == 'http://www.example.com/media/foo.txt'


def test_fallback_url_for_missing_file(inmemorystorage, filesystemstorage, settings):
    settings.FALLBACK_DATA_MIGRATION = True
    backend = get_storage_class()()

    assert backend.url('foo.txt') == 'http://www.example.com/media/foo.txt'
