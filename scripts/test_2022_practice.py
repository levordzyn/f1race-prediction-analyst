import fastf1

year = 2022
for rnd in range(1, 5):
    try:
        ses = fastf1.get_session(year, rnd, 'R')
        ses.load(laps=False, telemetry=False, weather=False, messages=False)
        meeting_key = ses.session_info['Meeting']['Key']
        print(f'R{rnd}: meeting_key = {meeting_key}')
    except Exception as exc:
        print(f'R{rnd}: ERROR - {exc}')

# Check practice sessions for R1
for name in ('FP1', 'FP2', 'FP3'):
    try:
        ses = fastf1.get_session(2022, 1, name)
        ses.load(laps=False, telemetry=False, weather=False, messages=False)
        info = ses.session_info
        print(f'  {name}: Type={info.get("Type")}, Name={info.get("Name")}, Key={info.get("Key")}, MeetingKey={info.get("Meeting", {}).get("Key")}')
    except Exception as exc:
        print(f'  {name}: EXCEPTION: {exc}')