# PS3Forge

PS3Forge is a Windows editor and open-source tool for people who want to create their own 3D homebrew games for the PlayStation 3. The project was vibe-coded with ChatGPT.

> My dream became a reality thanks to ChatGPT.

Create scenes, import models, and script gameplay with Visual Blocks or C++. The visual editor is designed for 3D. You can also create 2D games by writing your own rendering and gameplay code in C++. Build with the PSL1GHT toolchain and test your own homebrew in RPCS3 or on a compatible PS3.

## Run from source

1. Install Python 3.12 on Windows with the Python launcher.
2. In PowerShell, run:

   ```powershell
   py -3.12 -m venv .venv
   & .\.venv\Scripts\python.exe -m pip install -r requirements-desktop.txt
   & .\.venv\Scripts\python.exe desktop.py
   ```

3. Open a project. Choose **C++ Script > New visual script** to create a block script.
4. To build a game, configure WSL and PSL1GHT in **Settings**, then choose **Build PS3**. Set your local RPCS3 executable in **Settings** before using **Run in RPCS3**.

For cross-object gameplay, add **Send event to object** to the button script and **When event received** to the door script. Give both blocks the same event name and set the target to the door object's name.

See [SCRIPTING.md](SCRIPTING.md), [ENGINE-0.9.md](ENGINE-0.9.md), and [PACKAGES.md](PACKAGES.md). Source code is under the [MIT license](LICENSE.txt). Third-party components and the example model retain their [own licenses](THIRD_PARTY/README.txt) and [credits](runtime/sample/SOURCES.md).
