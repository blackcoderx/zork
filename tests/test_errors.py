from cinder.errors import CinderError


def test_cinder_error_attributes():
    err = CinderError(400, "Bad request")
    assert err.status_code == 400
    assert err.message == "Bad request"
    assert str(err) == "Bad request"


def test_cinder_error_cancel_delete():
    err = CinderError.cancel_delete()
    assert err.status_code == 200
    assert err.message == "__cancel_delete__"
