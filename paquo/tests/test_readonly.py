import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path

import pytest
import shapely.geometry

from paquo.images import ImageProvider
from paquo.projects import QuPathProject


@pytest.fixture(scope='module')
def project_and_changes(svs_small):
    with tempfile.TemporaryDirectory(prefix='paquo-') as tmpdir:
        qp = QuPathProject(tmpdir)
        entry = qp.add_image(svs_small)
        entry.hierarchy.add_annotation(
            roi=shapely.geometry.Point(1, 2)
        )
        qp.save()
        project_path = qp.path.parent
        del qp

        last_changes = {}
        for file in project_path.glob("**/*.*"):
            p = str(file.absolute())
            last_changes[p] = file.stat().st_mtime

        yield project_path, last_changes


@pytest.fixture(scope='function')
def copy_svs_small(svs_small):
    with tempfile.TemporaryDirectory(prefix='paquo-') as tmpdir:
        new_path = Path(tmpdir) / svs_small.name
        shutil.copy(svs_small, new_path)
        yield new_path


@pytest.fixture(scope="function")
def readonly_project(project_and_changes):
    project_path, changes = project_and_changes
    qp = QuPathProject(project_path, mode="r")
    qp.__changes = changes
    yield qp


@contextmanager
def assert_no_modification(qp):
    ctime, mtime = qp.timestamp_creation, qp.timestamp_modification
    yield qp
    project_path = qp.path.parent
    files = project_path.glob("**/*.*")
    assert files
    for file in files:
        p = str(file.absolute())
        assert qp.__changes[p] == file.stat().st_mtime, f"{str(file.relative_to(project_path))} was modified"
    assert qp.timestamp_creation == ctime
    assert qp.timestamp_modification == mtime


def test_fixture(readonly_project):
    pass


class _Accessor:
    def __init__(self, instance):
        self._if = set(filter(lambda x: not x.startswith('_'), dir(type(instance))))
        self._i = instance

    def setattr(self, item, value):
        self._if.discard(item)
        setattr(self._i, item, value)

    def callmethod(self, method, *args, **kwargs):
        self._if.discard(method)
        return getattr(self._i, method)(*args, **kwargs)

    def unused_public_interface(self):
        return self._if


def test_project_attrs_and_methods(readonly_project, copy_svs_small):
    with assert_no_modification(readonly_project) as qp:
        a = _Accessor(qp)
        # these are readonly anyways
        with pytest.raises(AttributeError):
            a.setattr("path", "abc")
        with pytest.raises(AttributeError):
            a.setattr("version", "v123")
        with pytest.raises(AttributeError):
            a.setattr("java_object", 1)
        with pytest.raises(AttributeError):
            a.setattr("uri", "abc")
        with pytest.raises(AttributeError):
            a.setattr("timestamp_creation", "abc")
        with pytest.raises(AttributeError):
            a.setattr("timestamp_modification", "abc")
        with pytest.raises(AttributeError):
            a.setattr("images", [])

        # these dont do anything
        a.callmethod("is_readable")

        # modifiable: These should all raise AttributeError in readonly mode
        with pytest.raises(AttributeError):
            a.setattr("name", "abc")
        with pytest.raises(AttributeError):
            a.setattr("path_classes", ())

        # These should raise an IOError when readonly
        with pytest.raises(IOError):
            a.callmethod("add_image", "./image")
        with pytest.raises(IOError):
            a.callmethod("save")

        # test that we can reassign uri's even in readonly mode
        cur_uri = qp.images[0].uri
        new_uri = ImageProvider.uri_from_path(copy_svs_small)
        assert cur_uri != new_uri
        # test that this does not change the project
        a.callmethod("update_image_paths", uri2uri={cur_uri: new_uri})
        assert qp.images[0].uri == new_uri

        # make sure everything is covered in case we extend the classes later
        assert not a.unused_public_interface()