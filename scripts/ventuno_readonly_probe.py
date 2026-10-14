"""Privacy-sanitized read-only inventory on REAL VENTUNO Q runner hardware."""
import json
import os
from pathlib import Path
import platform
import re
import subprocess


def number(path):
    try:
        raw=Path(path).read_text(encoding="ascii").strip()
        return int(raw) if re.fullmatch(r"-?\d{1,20}",raw) else None
    except (OSError,UnicodeError,ValueError):
        return None


def text_file(path,limit=10000):
    try:
        return Path(path).read_text(encoding="utf-8",errors="replace")[:limit]
    except OSError:
        return ""


def memory():
    values={}
    for line in text_file("/proc/meminfo").splitlines():
        m=re.match(r"^(MemTotal|MemAvailable|SwapTotal):\s+(\d+)\s+kB$",line)
        if m:
            values[m.group(1)]=round(int(m.group(2))/1048576,2)
    return {"total_gib":values.get("MemTotal"),
            "available_gib":values.get("MemAvailable"),
            "swap_total_gib":values.get("SwapTotal")}


def temperature():
    readings=[]
    for zone in sorted(Path("/sys/class/thermal").glob("thermal_zone[0-9]*"))[:128]:
        milli=number(zone/"temp")
        if milli is not None and -20000 <= milli <= 140000:
            readings.append(round(milli/1000,1))
    return {"sensor_count":len(readings),
            "min_c":min(readings) if readings else None,
            "max_c":max(readings) if readings else None}


def clocks():
    mhz=[]
    for cpu in sorted(Path("/sys/devices/system/cpu").glob("cpu[0-9]*"))[:32]:
        khz=number(cpu/"cpufreq/scaling_cur_freq")
        if khz is not None and 10000 <= khz <= 10000000:
            mhz.append(round(khz/1000))
    return {"sampled_cores":len(mhz),
            "min_mhz":min(mhz) if mhz else None,
            "max_mhz":max(mhz) if mhz else None}


def disk():
    try:
        v=os.statvfs("/")
        return {"total_gib":round(v.f_blocks*v.f_frsize/1073741824,2),
                "available_gib":round(v.f_bavail*v.f_frsize/1073741824,2)}
    except OSError:
        return {"total_gib":None,"available_gib":None}


def usb_audio():
    usb=0
    try:
        for dev in Path("/sys/bus/usb/devices").iterdir():
            if (dev/"idVendor").is_file() and (dev/"idProduct").is_file():
                usb+=1
    except OSError:
        pass
    cards=[x for x in Path("/sys/class/sound").glob("card[0-9]*")
           if re.fullmatch(r"card\d+",x.name)][:64]
    usb_cards=0
    for card in cards:
        try:
            if "/usb" in str(card.resolve()):
                usb_cards+=1
        except (OSError,RuntimeError):
            pass
    return {"usb_device_count":usb,"alsa_card_count":len(cards),
            "usb_audio_card_count":usb_cards,
            "usb_audio_present":usb_cards>0}


def connectivity():
    wifi=wifi_up=wired=0
    try:
        interfaces=list(Path("/sys/class/net").iterdir())[:64]
    except OSError:
        interfaces=[]
    for dev in interfaces:
        name=dev.name
        if name=="lo":
            continue
        wireless=(dev/"wireless").exists() or name.startswith("wl")
        if wireless:
            wifi+=1
            if text_file(dev/"operstate",16).strip()=="up":
                wifi_up+=1
        elif name.startswith(("en","eth")):
            wired+=1
    return {"wifi_interface_count":wifi,"wifi_link_up_count":wifi_up,
            "ethernet_interface_count":wired,
            "bluetooth_hci_count":len(list(Path("/sys/class/bluetooth").glob("hci[0-9]*"))[:32])}


def accelerators():
    # Device indicators, NOT proof of operational NPU inference.
    return {"qaic_nodes":len(list(Path("/dev").glob("qaic[0-9]*"))[:16]),
            "generic_accel_nodes":len(list(Path("/dev/accel").glob("accel[0-9]*"))[:16]),
            "gpu_render_nodes":len(list(Path("/dev/dri").glob("renderD[0-9]*"))[:16]),
            "kgsl_gpu_node":Path("/dev/kgsl-3d0").exists()}


def units():
    result={"myai":"not_listed","geniex":"not_listed","github_runner":"not_listed"}
    for command in (
        ["systemctl","--no-pager","--no-legend","--plain","list-units","--all","--type=service"],
        ["systemctl","--user","--no-pager","--no-legend","--plain","list-units","--all","--type=service"],
    ):
        try:
            proc=subprocess.run(command,capture_output=True,text=True,timeout=4,check=False)
        except (OSError,subprocess.TimeoutExpired):
            continue
        if proc.returncode:
            continue
        for line in proc.stdout.splitlines()[:1000]:
            words=line.split()
            if len(words)<4 or not words[0].endswith(".service"):
                continue
            name=words[0].lower()
            state=words[2] if words[2] in ("active","inactive","failed") else "other"
            if "geniex" in name:
                result["geniex"]=state
            elif name.startswith("actions.runner.") and "ventuno" in name:
                result["github_runner"]=state
            elif "myai" in name and not name.startswith("actions.runner."):
                result["myai"]=state
    return result


def report():
    uptime=text_file("/proc/uptime",40).split()
    try:
        hours=round(float(uptime[0])/3600,1) if uptime else None
    except (IndexError,ValueError):
        hours=None
    return {
        "probe":"ventuno_readonly",
        "platform":{"architecture":platform.machine(),"kernel":platform.release(),
                    "logical_cpus":os.cpu_count(),"uptime_hours":hours},
        "cpu_frequencies":clocks(),"thermal":temperature(),"memory":memory(),
        "root_disk":disk(),"usb_audio":usb_audio(),"network":connectivity(),
        "accelerator_indicators_only":accelerators(),"services":units(),
        "privacy":{"audio_recorded":False,"device_identifiers_exported":False,
                   "network_addresses_exported":False,"services_modified":False}
    }


if __name__=="__main__":
    print("MYAI_VENTUNO_READONLY_PROBE_JSON="+json.dumps(report(),sort_keys=True))
