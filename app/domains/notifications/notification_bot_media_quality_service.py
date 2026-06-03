import logging

from app.infra.clients.media_server_client import media_api


logger = logging.getLogger("uvicorn")

_media_api_provider = lambda: media_api
_logger_provider = lambda: logger
_admin_id_provider = lambda: get_admin_id


def set_dependency_providers(
    *,
    media_api_provider=None,
    logger_provider=None,
    admin_id_provider=None,
):
    global _media_api_provider
    global _logger_provider
    global _admin_id_provider

    if media_api_provider is not None:
        _media_api_provider = media_api_provider
    if logger_provider is not None:
        _logger_provider = logger_provider
    if admin_id_provider is not None:
        _admin_id_provider = admin_id_provider


def _empty_quality_info():
    return {
        "quality": "",
        "video_codec": "",
        "audio_codec": "",
        "resolution": "",
        "hdr": "",
        "quality_icon": "",
    }


def get_admin_id():
    try:
        res = _media_api_provider().get("/Users", timeout=5)
        if res.status_code == 200:
            users = res.json()
            for u in users:
                if u.get("Policy", {}).get("IsAdministrator"):
                    return u["Id"]
            if users:
                return users[0]["Id"]
    except Exception:
        pass
    return None


def get_media_quality_info(item_id: str) -> dict:
    """从 Emby 获取媒体质量信息（分辨率、编码、HDR等）"""
    result = _empty_quality_info()
    try:
        admin_id = _admin_id_provider()()
        if not admin_id:
            return result

        media_api_obj = _media_api_provider()
        logger_obj = _logger_provider()

        item_resp = media_api_obj.get(f"/Users/{admin_id}/Items/{item_id}", timeout=10)
        if not item_resp or item_resp.status_code != 200:
            logger_obj.warning(f"[媒体质量] 获取 item {item_id} 失败")
            return result

        item_data = item_resp.json()

        for ms in item_data.get("MediaSources", []):
            path = ms.get("Path", "") or ms.get("Name", "")
            if path:
                path_upper = path.upper()

                if "REMUX" in path_upper:
                    result["quality"] = "REMUX"
                    result["quality_icon"] = "🎬"

                if "2160P" in path_upper or "4K" in path_upper or "UHD" in path_upper:
                    if result["quality"]:
                        result["quality"] += " 4K"
                    else:
                        result["quality"] = "4K"
                    result["resolution"] = "3840×2160"
                elif "1080P" in path_upper or "FHD" in path_upper:
                    if result["quality"]:
                        result["quality"] += " 1080p"
                    else:
                        result["quality"] = "1080p"
                    result["resolution"] = "1920×1080"
                elif "720P" in path_upper or "HD" in path_upper:
                    if result["quality"]:
                        result["quality"] += " 720p"
                    else:
                        result["quality"] = "720p"
                    result["resolution"] = "1280×720"

                if "DOLBY.VISION" in path_upper or ".DV." in path_upper or "-DV" in path_upper:
                    result["hdr"] = "杜比视界"
                    result["quality_icon"] = "✨"
                    if result["quality"]:
                        result["quality"] += " 杜比视界"
                elif "HDR10+" in path_upper or "HDR10PLUS" in path_upper:
                    result["hdr"] = "HDR10+"
                    result["quality_icon"] = "✨"
                    if result["quality"]:
                        result["quality"] += " HDR10+"
                elif "HDR10" in path_upper:
                    result["hdr"] = "HDR10"
                    result["quality_icon"] = "✨"
                    if result["quality"]:
                        result["quality"] += " HDR10"
                elif "HDR" in path_upper:
                    result["hdr"] = "HDR"
                    result["quality_icon"] = "✨"
                    if result["quality"]:
                        result["quality"] += " HDR"

                if "H.265" in path_upper or "HEVC" in path_upper or "H265" in path_upper:
                    result["video_codec"] = "HEVC"
                elif "H.264" in path_upper or "AVC" in path_upper or "H264" in path_upper:
                    result["video_codec"] = "AVC"
                elif "AV1" in path_upper:
                    result["video_codec"] = "AV1"

                if "DTS-HD.MA" in path_upper or "DTSHDMA" in path_upper:
                    result["audio_codec"] = "DTS-HD MA"
                elif "DTS-HD" in path_upper or "DTSHD" in path_upper:
                    result["audio_codec"] = "DTS-HD"
                elif "TRUEHD" in path_upper:
                    result["audio_codec"] = "TrueHD"
                elif "DTS" in path_upper:
                    result["audio_codec"] = "DTS"
                elif "AC3" in path_upper or "DD" in path_upper:
                    result["audio_codec"] = "AC3"
                elif "EAC3" in path_upper or "DD+" in path_upper:
                    result["audio_codec"] = "E-AC3"
                elif "AAC" in path_upper:
                    result["audio_codec"] = "AAC"

                if result["quality"]:
                    logger_obj.info(f"[媒体质量] {result['quality']} | {result['video_codec']} | {result['audio_codec']}")
                    return result
                break

        media_streams = []

        media_sources = item_data.get("MediaSources", [])
        if media_sources:
            for ms in media_sources:
                if ms.get("MediaStreams"):
                    media_streams = ms["MediaStreams"]
                    break

        if not media_streams:
            media_streams = item_data.get("MediaStreams", [])

        if not media_streams:
            for fields in ["MediaStreams,MediaSources", "MediaStreams"]:
                detail_resp = media_api_obj.get(f"/Users/{admin_id}/Items/{item_id}?Fields={fields}", timeout=10)
                if detail_resp and detail_resp.status_code == 200:
                    detail_data = detail_resp.json()
                    for ms in detail_data.get("MediaSources", []):
                        if ms.get("MediaStreams"):
                            media_streams = ms["MediaStreams"]
                            break
                    if not media_streams:
                        media_streams = detail_data.get("MediaStreams", [])
                    if media_streams:
                        break

        if not media_streams:
            playback_resp = media_api_obj.post(f"/Items/{item_id}/PlaybackInfo?UserId={admin_id}", json={}, timeout=10)
            if playback_resp and playback_resp.status_code == 200:
                playback_data = playback_resp.json()
                for ms in playback_data.get("MediaSources", []):
                    if ms.get("MediaStreams"):
                        media_streams = ms["MediaStreams"]
                        break

        if not media_streams:
            logger_obj.warning(f"[媒体质量] 未找到 MediaStreams, item_id={item_id}")
            return result

        video_stream = None
        audio_stream = None
        for stream in media_streams:
            if stream.get("Type") == "Video" and not video_stream:
                video_stream = stream
            elif stream.get("Type") == "Audio" and not audio_stream:
                audio_stream = stream

        if video_stream:
            width = video_stream.get("Width", 0)
            height = video_stream.get("Height", 0)
            bit_rate = video_stream.get("BitRate", 0)

            is_remux = False
            for ms in item_data.get("MediaSources", []):
                path = ms.get("Path", "") or ms.get("Name", "")
                if path and "REMUX" in path.upper():
                    is_remux = True
                    break

            if not is_remux and bit_rate and bit_rate > 30000000:
                for stream in media_streams:
                    if stream.get("Type") == "Audio":
                        audio_codec = (stream.get("Codec") or "").upper()
                        if audio_codec in ["TRUEHD", "DTSHD", "DTSHDMA", "DTS"]:
                            is_remux = True
                            break

            if height >= 2160 or width >= 3840:
                quality_label = "4K"
                quality_icon = "🎬"
            elif height >= 1080:
                quality_label = "1080p"
                quality_icon = "📺"
            elif height >= 720:
                quality_label = "720p"
                quality_icon = "📱"
            elif height >= 480:
                quality_label = "480p"
                quality_icon = "💾"
            else:
                quality_label = f"{height}p"
                quality_icon = "📼"

            hdr_info = ""
            video_range = video_stream.get("VideoRange", "")
            extended_sub = video_stream.get("ExtendedVideoSubType", "")
            hdr_format = video_stream.get("HdrFormat", "")
            color_transfer = video_stream.get("ColorTransfer", "")

            if video_range:
                vr_upper = video_range.upper()
                if "DOLBY" in vr_upper or vr_upper == "DV":
                    hdr_info = "杜比视界"
                elif vr_upper == "HDR10":
                    hdr_info = "HDR10"
                elif vr_upper == "HLG":
                    hdr_info = "HLG"
                elif vr_upper == "HDR":
                    hdr_info = "HDR"

            if not hdr_info and extended_sub:
                ext_upper = extended_sub.upper()
                if "DOVI" in ext_upper or "DOLBY" in ext_upper or "DV" in ext_upper:
                    if "PROFILE5" in ext_upper or "PROFILE50" in ext_upper:
                        hdr_info = "杜比视界 P5"
                    elif "PROFILE7" in ext_upper or "PROFILE70" in ext_upper:
                        hdr_info = "杜比视界 P7"
                    elif "PROFILE8" in ext_upper or "PROFILE80" in ext_upper:
                        hdr_info = "杜比视界 P8"
                    else:
                        hdr_info = "杜比视界"
                elif "HDR10PLUS" in ext_upper or "HDR10+" in ext_upper:
                    hdr_info = "HDR10+"
                elif "HDR10" in ext_upper:
                    hdr_info = "HDR10"
                elif "HDR" in ext_upper:
                    hdr_info = "HDR"
                elif "HLG" in ext_upper:
                    hdr_info = "HLG"

            if not hdr_info and color_transfer:
                ct_lower = color_transfer.lower()
                if "smpte2084" in ct_lower or "pq" in ct_lower:
                    hdr_info = "HDR"
                elif "arib-std-b67" in ct_lower or "hlg" in ct_lower:
                    hdr_info = "HLG"

            if not hdr_info and (video_stream.get("IsHDR") or hdr_format):
                if "DV" in hdr_format or "Dolby Vision" in hdr_format:
                    hdr_info = "杜比视界"
                elif "HDR10Plus" in hdr_format or "HDR10+" in hdr_format:
                    hdr_info = "HDR10+"
                elif "HDR10" in hdr_format:
                    hdr_info = "HDR10"
                else:
                    hdr_info = "HDR"

            if hdr_info:
                quality_icon = "✨"

            video_codec = video_stream.get("Codec", "")
            codec_display = {
                "hevc": "HEVC",
                "h265": "HEVC",
                "avc": "AVC",
                "h264": "AVC",
                "av1": "AV1",
                "vp9": "VP9",
            }.get(video_codec.lower(), video_codec.upper() if video_codec else "")

            result["resolution"] = f"{width}×{height}" if width and height else ""
            result["video_codec"] = codec_display
            result["hdr"] = hdr_info

            quality_parts = []
            if is_remux:
                quality_parts.append("REMUX")
            quality_parts.append(quality_label)
            if hdr_info:
                quality_parts.append(hdr_info)
            result["quality"] = " ".join(quality_parts)
            result["quality_icon"] = quality_icon

        if audio_stream:
            audio_codec = audio_stream.get("Codec", "")
            audio_channels = audio_stream.get("Channels", 0)

            audio_display = {
                "dts": "DTS",
                "dtshd": "DTS-HD",
                "dtshdma": "DTS-HD MA",
                "truehd": "TrueHD",
                "ac3": "AC3",
                "eac3": "E-AC3",
                "aac": "AAC",
                "flac": "FLAC",
                "opus": "Opus",
            }.get(audio_codec.lower(), audio_codec.upper() if audio_codec else "")

            channel_display = {2: "2.0", 6: "5.1", 8: "7.1"}.get(audio_channels, f"{audio_channels}ch")

            result["audio_codec"] = f"{audio_display} {channel_display}" if audio_display else ""

    except Exception as e:
        _logger_provider().error(f"获取媒体质量信息失败: {e}")

    return result
