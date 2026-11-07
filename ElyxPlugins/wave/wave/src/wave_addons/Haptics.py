try:
    __file__
except NameError:
    try:
        __file__ = file
    except NameError:
        __file__ = ""

try:
    from java import jclass, jarray, jlong, jint
except Exception:
    jclass = None

_vib = None


def _vibrator(ctx):
    global _vib
    if _vib is not None:
        return _vib
    try:
        if int(jclass("android.os.Build$VERSION").SDK_INT) >= 31:
            vm = ctx.getSystemService("vibrator_manager")
            if vm is not None:
                _vib = vm.getDefaultVibrator()
                return _vib
    except Exception:
        pass
    try:
        _vib = ctx.getSystemService("vibrator")
    except Exception:
        _vib = None
    return _vib


def build_pattern(style, crossings, length, gap):
    out = []
    for i in range(max(1, min(4, int(crossings)))):
        pre = 0 if i == 0 else 6
        if style == 0:
            out += [pre, length, gap, length]
        elif style == 2:
            out += [pre, int(length * 2.2)]
        else:
            out += [pre, length]
    return out


def ratchet(ctx, style, crossings, strength, length, gap):
    v = _vibrator(ctx)
    if v is None:
        return
    try:
        pattern = build_pattern(int(style), crossings, int(length), int(gap))
        amp = max(1, min(255, int(40 + 215 * (float(strength) / 100.0))))
        VE = jclass("android.os.VibrationEffect")
        timings = jarray(jlong)([int(x) for x in pattern])
        try:
            v.cancel()
        except Exception:
            pass
        try:
            has_amp = bool(v.hasAmplitudeControl())
        except Exception:
            has_amp = False
        if has_amp:
            amps = jarray(jint)([0 if i % 2 == 0 else amp for i in range(len(pattern))])
            v.vibrate(VE.createWaveform(timings, amps, -1))
        else:
            v.vibrate(VE.createWaveform(timings, -1))
    except Exception:
        try:
            v.vibrate(int(length))
        except Exception:
            pass
