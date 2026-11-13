content = open(r'C:\Users\outbnx_\Documents\F1 PROJECTS\f1pred\cli.py', 'rb').read()

old = b'''    #
    mode, warnings, fatal = choose_mode(info, args.mode)
    if mode is None:
        print(f"ERROR: cannot forecast {year} R{rnd} in mode "
              f"'{args.mode}'.")
        for f in fatal:
            print()
            _wrap("ERROR: " + f)
        print()
        _wrap("Fix: pass --mode early once practice has run, or --mode full "
              "once qualifying has run, or --mode auto to let the data "
              "decide.")
        con.close()
        return 1

    # -----------------------------------------'''

new = b'''    #
    mode, warnings, fatal = choose_mode(info, args.mode)
    if mode is None:
        print(f"ERROR: cannot forecast {year} R{rnd} in mode "
              f"'{args.mode}'.")
        for f in fatal:
            print()
            _wrap("ERROR: " + f)
        print()
        _wrap("Fix: pass --mode early once practice has run, or --mode full "
              "once qualifying has run, or --mode auto to let the data "
              "decide.")
        con.close()
        return 1

    # Refuse to run walk-forward evaluation on already-run races.
    # A forecast must be for a race that has not run yet.
    if not is_forecast:
        print(f"ERROR: {year} R{rnd} already has {info['results']} result row(s) - "
              f"that is a result, not a forecast. A forecast may only be run "
              f"while the race is unrun.")
        _wrap("Use --save on a race that has not run yet. Once results exist, "
              "the forecast window has closed. For model evaluation on historical "
              "races, use the walk-forward scripts directly.")
        con.close()
        return 1

    # -----------------------------------------'''

if old in content:
    content = content.replace(old, new)
    open(r'C:\Users\outbnx_\Documents\F1 PROJECTS\f1pred\cli.py', 'wb').write(content)
    print('Replacement done')
else:
    print('Old string not found')
    idx = content.find(b'choose_mode(info, args.mode)')
    if idx >= 0:
        print('Found at:', idx)
        print(content[idx:idx+500])