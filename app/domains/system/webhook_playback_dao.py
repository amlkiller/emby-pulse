from app.infra.db.local_playback_store import insert_webhook_playback_ip_record
from app.utils.ip_location import get_isp, get_location


def save_webhook_playback_ip_data(data, user_id, user_name, item, ip) -> None:
    location = get_location(ip)
    isp = get_isp(ip)
    item_id = item.get("Id", "")
    item_name = item.get("Name", "未知内容")
    session = data.get("Session") or data
    client = session.get("Client") or data.get("Client", "")
    device = session.get("DeviceName") or data.get("DeviceName", "")

    insert_webhook_playback_ip_record(
        user_id=user_id,
        user_name=user_name,
        item_id=item_id,
        item_name=item_name,
        date_created=data.get("Date", ""),
        client=client,
        device_name=device,
        remote_endpoint=ip,
        location=location,
        isp=isp,
    )
