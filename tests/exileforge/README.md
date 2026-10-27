# ExileForge integration checks

Run these checks from the repository root on Windows with Python 3.9 or newer:

```powershell
python tests/exileforge/test_localexile.py -v
```

The default runtime is this checkout's `runtime` folder. To use another complete
ExileForge/PoB runtime, pass its directory explicitly:

```powershell
python tests/exileforge/test_localexile.py --runtime-dir 'F:\evry\evryPath\ExileForge' -v
```

The tests always load the integration module from this source checkout,
`src/Modules/LocalExile.lua`. They use the selected runtime's actual Lua, JSON and
curl libraries. No installed PoB files, saved builds, settings or account tokens
are read or changed.

The harness supplies small in-memory controls to exercise the button callbacks,
active-build export request, preview/create routing, result and error messages,
protected token field and token cleanup. Preferences are written only to a
temporary test profile. A temporary loopback HTTP server checks the actual curl
request and proves that redirects are refused without forwarding its synthetic
token.

These checks require no LocalExile receiver or game client. They cover integration
behavior rather than native GUI rendering. On other operating systems, the suite
reports an explicit skip because the bundled runtime libraries are Windows DLLs.
