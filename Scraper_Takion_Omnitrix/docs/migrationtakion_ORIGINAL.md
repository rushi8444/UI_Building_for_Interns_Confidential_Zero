# Takion Omnitrix Migration Guide (Manual Python Execution)

This guide walks you through exactly how to set up the new PC to run the raw Python script (`omnitrix_automation.py`) manually instead of using the compiled `.exe`.

## 1. Prerequisites (On the New PC)
Since you want to run the raw Python code, the new PC must have Python installed.
1. Download Python (version 3.10 to 3.14 recommended) from `python.org`.
2. **IMPORTANT:** During the Python installation, make sure to check the box that says **"Add Python to PATH"** before clicking Install.

## 2. Install Required Python Modules
Once Python is installed, you need to download the specialized packages that the Omnitrix script uses to do math and talk to Windows pipes.
Open your Windows Command Prompt (`cmd.exe`) and run this exact command:
```cmd
pip install pywin32 pandas numpy pyarrow pytz
```
*Wait for it to say "Successfully installed...".*

## 3. Install Takion Dependencies
Since Takion is a C++ application, you must ensure the new PC has the Microsoft runtimes to load the `TakionAdditionalColumns.dll`.
1. Plug in your Pendrive.
2. Double-click the file named `Install_First_VC_Redist.exe`.
3. Follow the prompts to install it. (This fixes the `0xc000007b` and missing module errors).

## 4. Setup Takion
1. On your Pendrive, go to the `Takion_DLL` folder.
2. Copy `TakionAdditionalColumns.dll`.
3. Paste it directly into your new PC's Takion folder (e.g. `C:\Takion\`).
4. Open Takion, go to **Configuration -> Extensions -> Add**, and select the DLL.
5. Restart Takion so the DLL injects into memory.

## 5. Run the Omnitrix Strategy
1. Copy `omnitrix_automation.py` from your Pendrive onto the new PC (for example, to your Desktop).
2. Open Windows Command Prompt (`cmd.exe`).
3. Navigate to where you saved the file:
   ```cmd
   cd C:\Users\YourUsername\Desktop
   ```
4. Run the script:
   ```cmd
   python omnitrix_automation.py
   ```

You will see the cyan output: `[10:15:30] Omnitrix Holy Grail: Passive Liquidity Market Maker Initialized.`

You are now successfully trading!