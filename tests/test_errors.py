from zeno.errors import ZenoError


def test_zeno_error_attributes():
    err = ZenoError(400, "Bad request")
    assert err.status_code == 400
    assert err.message == "Bad request"
    assert str(err) == "Bad request"


def test_zeno_error_cancel_delete():
    err = ZenoError.cancel_delete()
    assert err.status_code == 200
    assert err.message == "__cancel_delete__"
