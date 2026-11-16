# Third-party notices

FNauto's own source and documentation are MIT-licensed (see `LICENSE`). The
following components are used at runtime or to build the Windows release. The
license identifiers describe the upstream projects; follow the linked notices
when redistributing.

## Runtime dependencies

| Component | Pinned version | License | Upstream |
|---|---|---|---|
| Python runtime (bundled by PyInstaller) | 3.14.x | PSF-2.0 | <https://docs.python.org/3/license.html> |
| NumPy | 2.5.4 | BSD-3-Clause | <https://numpy.org/doc/stable/license.html> |
| OpenCV Python (`opencv-python`) | 5.0.0.93 | Apache-2.0 (OpenCV); wheel includes its own third-party notices | <https://github.com/opencv/opencv/blob/4.x/LICENSE> |
| mss | 10.2.0 | MIT | <https://github.com/BoboTiG/python-mss> |
| Pillow | 13.0.0 | HPND | <https://python-pillow.org/about/#license> |
| pydirectinput | 1.0.4 | MIT | <https://github.com/learncodebygaming/pydirectinput> |
| keyboard | 0.13.5 | MIT | <https://github.com/boppreh/keyboard> |
| PySide6 / Qt 6 | 6.12.0 | LGPL-3.0 (also GPLv3/commercial) | <https://www.qt.io/licensing/open-source-lgpl-obligations> |

## Build and test tools

These are development dependencies and are not part of the runtime feature set:

| Component | Pinned version | License |
|---|---|---|
| PyInstaller | 6.22.3 | GPL-2.0-or-later with the PyInstaller bootloader exception |
| pytest | 9.2.0 | MIT |
| Ruff | 0.17.5 | MIT |
| Vulture | 2.16 | MIT |

The optional `cloudflared.exe` binary is **not bundled**. It is downloaded or
installed by the user from Cloudflare's official releases and remains under
Cloudflare's Apache-2.0 license. See <https://github.com/cloudflare/cloudflared>.

## Bundled fonts

The following font files are included in `assets/fonts/` and are used by the
desktop UI:

- **Inter** — `Inter-Regular.ttf`, `Inter-Bold.ttf`, `inter-latin.ttf`.
  Copyright 2020 The Inter Project Authors (<https://github.com/rsms/inter>).
- **Outfit** — `Outfit-Regular.ttf`, `Outfit-Bold.ttf`, `outfit-latin.ttf`.
  Copyright 2021 The Outfit Project Authors
  (<https://github.com/Outfitio/Outfit-Fonts>).

Both font families are licensed under the SIL Open Font License, Version 1.1.
The complete license texts are included in `assets/fonts/OFL-Inter.txt` and
`assets/fonts/OFL-Outfit.txt`; the full OFL text is reproduced below.

The template PNG files in `assets/` depict game UI elements. They are not
claimed under the project's MIT license; the game artwork belongs to its
respective owners and is used only for local screen matching.

## PySide6 / Qt LGPL note

The Windows executable is built in **one-directory** mode. Qt and PySide6
libraries remain separate DLLs beside `FNauto.exe`; they are dynamically linked
and can be replaced with compatible builds. FNauto does not modify those
libraries. If you redistribute the application, keep this notice and the
applicable LGPLv3 text and make the corresponding library source available as
required by the license. Qt's own licensing page and the PySide6 package
metadata contain the authoritative terms.

## SIL Open Font License 1.1

Copyright 2020 The Inter Project Authors (https://github.com/rsms/inter)
Copyright 2021 The Outfit Project Authors (https://github.com/Outfitio/Outfit-Fonts)

This Font Software is licensed under the SIL Open Font License, Version 1.1.
This license is copied below, and is also available with a FAQ at:
https://scripts.sil.org/OFL

-----------------------------------------------------------
SIL OPEN FONT LICENSE Version 1.1 - 26 February 2007
-----------------------------------------------------------

PREAMBLE
The goals of the Open Font License (OFL) are to stimulate worldwide
development of collaborative font projects, to support the font creation
efforts of academic and linguistic communities, and to provide a free and
open framework in which fonts may be shared and improved in partnership
with others.

The OFL allows the licensed fonts to be used, studied, modified and
redistributed freely as long as they are not sold by themselves. The
fonts, including any derivative works, can be bundled, embedded,
redistributed and/or sold with any software provided that any reserved
names are not used by derivative works. The fonts and derivatives,
however, cannot be released under any other type of license. The
requirement for fonts to remain under this license does not apply
to any document created using the fonts or their derivatives.

DEFINITIONS
"Font Software" refers to the set of files released by the Copyright
Holder(s) under this license and clearly marked as such. This may
include source files, build scripts and documentation.

"Reserved Font Name" refers to any names specified as such after the
copyright statement(s).

"Original Version" refers to the collection of Font Software components as
distributed by the Copyright Holder(s).

"Modified Version" refers to any derivative made by adding to, deleting,
or substituting -- in part or in whole -- any of the components of the
Original Version, by changing formats or by porting the Font Software to a
new environment.

"Author" refers to any designer, engineer, programmer, technical
writer or other person who contributed to the Font Software.

PERMISSION & CONDITIONS
Permission is hereby granted, free of charge, to any person obtaining
a copy of the Font Software, to use, study, copy, merge, embed, modify,
redistribute, and sell modified and unmodified copies of the Font
Software, subject to the following conditions:

1) Neither the Font Software nor any of its individual components,
in Original or Modified Versions, may be sold by itself.

2) Original or Modified Versions of the Font Software may be bundled,
redistributed and/or sold with any software, provided that each copy
contains the above copyright notice and this license. These can be
included either as stand-alone text files, human-readable headers or
in the appropriate machine-readable metadata fields within text or
binary files as long as those fields can be easily viewed by the user.

3) No Modified Version of the Font Software may use the Reserved Font
Name(s) unless explicit written permission is granted by the corresponding
Copyright Holder. This restriction only applies to the primary font name as
presented to the users.

4) The name(s) of the Copyright Holder(s) or the Author(s) of the Font
Software shall not be used to promote, endorse or advertise any
Modified Version, except to acknowledge the contribution(s) of the
Copyright Holder(s) and the Author(s) or with their explicit written
permission.

5) The Font Software, modified or unmodified, in part or in whole,
must be distributed entirely under this license, and must not be
distributed under any other license. The requirement for fonts to
remain under this license does not apply to any document created
using the Font Software.

TERMINATION
This license becomes null and void if any of the above conditions are
not met.

DISCLAIMER
THE FONT SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO ANY WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT
OF COPYRIGHT, PATENT, TRADEMARK, OR OTHER RIGHT. IN NO EVENT SHALL THE
COPYRIGHT HOLDER BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
INCLUDING ANY GENERAL, SPECIAL, INDIRECT, INCIDENTAL, OR CONSEQUENTIAL
DAMAGES, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF THE USE OR INABILITY TO USE THE FONT SOFTWARE OR FROM
OTHER DEALINGS IN THE FONT SOFTWARE.
