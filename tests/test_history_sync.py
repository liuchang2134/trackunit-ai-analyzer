from datetime import datetime, timezone, timedelta
import pytest
from scripts.sync_trackunit_history import fetch_history
from app.trackunit_client import TrackunitError

SNAPSHOT={"EquipmentHeader":{"PIN":"PIN/with space","Model":"EX","SerialNumber":"DEMO"},"metadata":{"assetId":"A"}}
START=datetime(2026,1,1,tzinfo=timezone.utc)
END=START+timedelta(days=1)


class Client:
    def __init__(self, fail_idle=False):
        self.calls=[]
        self.fail_idle=fail_idle
    def request(self, method, endpoint):
        self.calls.append(endpoint)
        assert method=="GET" and "PIN%2Fwith%20space" in endpoint
        assert endpoint.endswith("/1")
        if "CumulativeOperatingHours" in endpoint:
            return {"cumulativeOperatingHours":[{"Hour":0,"datetime":START.isoformat()}]}
        if self.fail_idle:
            raise TrackunitError("sensitive provider details")
        return {"cumulativeIdleHours":[]}


def test_sync_keeps_empty_idle_and_blocks_repeat(tmp_path):
    client=Client()
    result=fetch_history(SNAPSHOT,START,END,client,tmp_path)
    assert result["dataset"].telemetry[0].operating_hours==0
    assert result["dataset"].telemetry[0].idle_hours is None
    assert result["verification"]["capabilities"][1]["status"]=="empty"
    with pytest.raises(ValueError,match="15 minutes"):
        fetch_history(SNAPSHOT,START,END,client,tmp_path)
    assert len(client.calls)==2


def test_failed_idle_does_not_become_empty_success(tmp_path):
    result=fetch_history(SNAPSHOT,START,END,Client(True),tmp_path)
    assert result["dataset"] is not None
    assert result["verification"]["capabilities"][1]["status"]=="error"
    assert "sensitive" not in str(result)


@pytest.mark.parametrize("start,end",[(START,START),(START,START+timedelta(days=15)),(START.replace(tzinfo=None),END)])
def test_invalid_window_never_makes_requests(tmp_path,start,end):
    client=Client()
    with pytest.raises(ValueError): fetch_history(SNAPSHOT,start,end,client,tmp_path)
    assert client.calls==[]


@pytest.mark.parametrize("code,status",[(401,"unauthorized"),(403,"unauthorized"),(429,"rate_limited")])
def test_http_status_survives_without_error_body(tmp_path,code,status):
    class FailedClient:
        def request(self,*args):raise TrackunitError("private",code)
    result=fetch_history(SNAPSHOT,START,END,FailedClient(),tmp_path)
    assert result["dataset"] is None
    assert result["verification"]["capabilities"][0]["status"]==status
    assert result["verification"]["capabilities"][0]["http_status"]==code
    assert "private" not in str(result)
