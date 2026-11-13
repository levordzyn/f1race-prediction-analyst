import fastf1

year = 2023
for name in ("FP1", "FP2", "FP3"):
    try:
        ses = fastf1.get_session(year, 1, name)
        ses.load(laps=False, telemetry=False, weather=False, messages=False)
        info = ses.session_info
        print(f"  {name}: Type={info.get('Type')}, Name={info.get('Name')}, Key={info.get('Key')}, MeetingKey={info.get('Meeting', {}).get('Key')}")
    except Exception as exc:
        print(f"  {name}: EXCEPTION: {exc}")