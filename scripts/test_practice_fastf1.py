import fastf1

year = 2023
for name in ("Practice 1", "Practice 2", "Practice 3", "FP1", "FP2", "FP3"):
    try:
        ses = fastf1.get_session(year, name)
        ses.load(laps=False, telemetry=False, weather=False, messages=False)
        info = ses.session_info
        print(f"  {name}: Type={info.get('Type')}, Name={info.get('Name')}, Key={info.get('Key')}, MeetingKey={info.get('Meeting', {}).get('Key')}")
        if info.get('Type') == 'Practice' and info.get('Name') in ('Practice 1', 'Practice 2', 'Practice 3', 'FP1', 'FP2', 'FP3'):
            print(f'    -> MATCH')
    except Exception as exc:
        print(f'  {name}: EXCEPTION: {exc}')
        continue