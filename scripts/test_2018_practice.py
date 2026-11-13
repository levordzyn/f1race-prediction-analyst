import fastf1

year = 2018
rnd = 1
# First get the meeting key from the race session
ses = fastf1.get_session(year, rnd, 'R')
ses.load(laps=False, telemetry=False, weather=False, messages=False)
meeting_key = ses.session_info['Meeting']['Key']
print('Meeting key:', meeting_key)

# Now try to get practice sessions
for name in ('FP1', 'FP2', 'FP3'):
    try:
        ses = fastf1.get_session(year, rnd, name)
        ses.load(laps=False, telemetry=False, weather=False, messages=False)
        info = ses.session_info
        print(f'{name}: Type={info.get("Type")}, Name={info.get("Name")}, Key={info.get("Key")}, MeetingKey={info.get("Meeting", {}).get("Key")}')
    except Exception as exc:
        print(f'{name}: EXCEPTION: {exc}')