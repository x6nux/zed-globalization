# ZedG Windows 安装程序（NSIS）
# 生成: zedg-setup-x64.exe / zedg-setup-arm64.exe
# 功能:
#   1. 释放 ZedG.exe + bin\ZedG.exe(cli) + 运行时库到安装目录
#   2. 可选组件"覆盖官方 Zed 安装"(默认不勾选):
#      - 将官方 %LOCALAPPDATA%\Programs\Zed\zed.exe 备份为 zed.exe.official.bak
#      - 复制 ZedG.exe 覆盖之 (生态工具/git difftool/终端 `zed` 命令自动识别)
#   3. 开始菜单/桌面快捷方式, PATH 注册(可选), 卸载完整还原

!define APP_NAME      "ZedG"
!define APP_PUBLISHER "zed-globalization"
!define OFFICIAL_DIR  "$LOCALAPPDATA\Programs\Zed"
!define OFFICIAL_EXE  "${OFFICIAL_DIR}\zed.exe"
!define BAK_FILE      "${OFFICIAL_DIR}\zed.exe.official.bak"

!include "MUI2.nsh"
!include "FileFunc.nsh"

Name "${APP_NAME}"
OutFile "..\zedg-setup.exe"
InstallDir "$LOCALAPPDATA\Programs\ZedG"
InstallDirRegKey HKCU "Software\${APP_NAME}" "InstallDir"
RequestExecutionLevel user

!define MUI_ABORTWARNING
!define MUI_ICON   "${NSISDIR}\Contrib\Graphics\Icons\modern-install.ico"
!define MUI_UNICON "${NSISDIR}\Contrib\Graphics\Icons\modern-uninstall.ico"

; --- 安装向导页 ---
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

; --- 卸载向导页 ---
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "SimpChinese"
!insertmacro MUI_LANGUAGE "English"

; ---------------------------------------------------------------------------
; 段: 主程序 (必装)
; ---------------------------------------------------------------------------
Section "${APP_NAME} 主程序 (必需)" SEC_MAIN
  SectionIn RO
  SetOutPath "$INSTDIR"

  File /oname=ZedG.exe "zed-dist\ZedG.exe"
  SetOutPath "$INSTDIR\bin"
  File /oname=ZedG.exe "zed-dist\bin\ZedG.exe"
  SetOutPath "$INSTDIR"

  ; 附带的运行时库 (libgit2 等, 若存在)
  File /nonfatal /oname=libgit2.dll "zed-dist\libgit2.dll"

  ; 写注册表 (卸载信息 + 安装目录记忆)
  WriteRegStr HKCU "Software\${APP_NAME}" "InstallDir" $INSTDIR
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
    "DisplayName" "${APP_NAME} — Zed 编辑器多语言版"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
    "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
    "DisplayIcon" "$INSTDIR\ZedG.exe"
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
    "EstimatedSize" 0x018000

  ; 卸载器
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  ; 开始菜单快捷方式
  CreateDirectory "$SMPROGRAMS\${APP_NAME}"
  CreateShortcut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\ZedG.exe"
  CreateShortcut "$SMPROGRAMS\${APP_NAME}\Uninstall.lnk" "$INSTDIR\Uninstall.exe"

  ; 桌面快捷方式
  CreateShortcut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\ZedG.exe"
SectionEnd

; ---------------------------------------------------------------------------
; 段: 添加到 PATH (可选, 默认关闭)
; ---------------------------------------------------------------------------
Section "将安装目录加入 PATH 环境变量" SEC_PATH
  ; EN_ADD_PATH 由 .onSelChange 维护, 与覆盖选项互斥提示
  Push "$INSTDIR\bin"
  Call AddToPath
SectionEnd

; ---------------------------------------------------------------------------
; 段: 覆盖官方 Zed 安装 (可选, 默认关闭 — issue #37 用户诉求)
; ---------------------------------------------------------------------------
Section /o "覆盖官方 Zed 安装 (生态兼容, 可随时还原)" SEC_OVERRIDE
  DetailPrint "检查官方 Zed 安装..."

  IfFileExists "${OFFICIAL_EXE}" 0 no_official

  ; 备份官方 zed.exe (仅首次; 已有备份不覆盖, 保留最原始版本)
  IfFileExists "${BAK_FILE}" 0 do_backup
    DetailPrint "官方备份已存在: zed.exe.official.bak (跳过备份)"
    Goto after_backup
  do_backup:
    CopyFiles /SILENT "${OFFICIAL_EXE}" "${BAK_FILE}"
    DetailPrint "已备份官方 zed.exe → zed.exe.official.bak"
  after_backup:

  ; 覆盖为 ZedG
  CopyFiles /SILENT "$INSTDIR\ZedG.exe" "${OFFICIAL_EXE}"
  DetailPrint "已将官方 zed.exe 替换为 ${APP_NAME}"

  ; 注册表记录覆盖状态, 卸载时还原
  WriteRegStr HKCU "Software\${APP_NAME}" "OverrideOfficial" "1"
  Goto done_override

  no_official:
    DetailPrint "未检测到官方 Zed (${OFFICIAL_EXE}), 跳过覆盖"
  done_override:
SectionEnd

; --- 覆盖与 PATH 的选择状态管理 ---
Var OverrideSelected

Function .onInit
  StrCpy $OverrideSelected "0"
FunctionEnd

Function .onSelChange
  Push $0
  SectionGetFlags ${SEC_OVERRIDE} $0
  IntOp $0 $0 & 1
  StrCpy $OverrideSelected "$0"
  Pop $0
FunctionEnd

; ---------------------------------------------------------------------------
; 安装完成动作
; ---------------------------------------------------------------------------
Function .onInstSuccess
  ; 记录版本信息
  WriteRegStr HKCU "Software\${APP_NAME}" "Version" "VERSION_PLACEHOLDER"
FunctionEnd

; ---------------------------------------------------------------------------
; 卸载
; ---------------------------------------------------------------------------
Section "Uninstall"
  ; 还原官方 zed.exe (若曾覆盖)
  ReadRegStr $0 HKCU "Software\${APP_NAME}" "OverrideOfficial"
  ${If} $0 == "1"
    IfFileExists "${BAK_FILE}" 0 skip_restore
      Delete "${OFFICIAL_EXE}"
      CopyFiles /SILENT "${BAK_FILE}" "${OFFICIAL_EXE}"
      Delete "${BAK_FILE}"
      DetailPrint "已还原官方 zed.exe"
    skip_restore:
  ${EndIf}

  ; 移除快捷方式
  Delete "$DESKTOP\${APP_NAME}.lnk"
  RMDir /r "$SMPROGRAMS\${APP_NAME}"

  ; 移除 PATH
  Push "$INSTDIR\bin"
  Call un.RemoveFromPath

  ; 删除主程序 (卸载器自身除外)
  Delete "$INSTDIR\ZedG.exe"
  Delete "$INSTDIR\bin\ZedG.exe"
  Delete "$INSTDIR\libgit2.dll"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR\bin"
  RMDir "$INSTDIR"

  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"
  DeleteRegKey /ifempty HKCU "Software\${APP_NAME}"
SectionEnd

; ---------------------------------------------------------------------------
; PATH 操作宏 (HKCU 环境变量, 用户级, 不需要管理员)
; ---------------------------------------------------------------------------
!macro _AddToPathImpl
Function AddToPath
  Exch $0
  Push $1
  Push $2
  ReadRegStr $1 HKCU "Environment" "Path"
  ; 已包含则跳过
  Push "$1;"
  Push ";$0;"
  Call StrContains
  Pop $2
  StrCmp $2 "" 0 done
    StrCpy $1 "$1;$0"
    WriteRegExpandStr HKCU "Environment" "Path" "$1"
    ; 广播环境变量变更, 让新开的终端立刻看到
    SendMessage ${HWND_BROADCAST} ${WM_WININICHANGE} 0 "STR:Environment" /TIMEOUT=2000
  done:
    Pop $2
    Pop $1
    Pop $0
FunctionEnd
!macroend
!insertmacro _AddToPathImpl

!macro StrRep output string search replace
      Push `${string}`
      Push `${search}`
      Push `${replace}`
      !ifndef __UNINSTALL__
        Call StrRep
      !else
        Call un.StrRep
      !endif
      Pop ${output}
    !macroend
    Function StrRep
      Exch $R2 ; replace
      Exch $R1 ; search
      Exch 2
      Exch $R0 ; string
      Push $R3
      Push $R4
      Push $R5
      Push $R6
      StrCpy $R3 0
      StrLen $R4 $R1
      loop:
        StrCpy $R5 $R0 $R4 $R3
        StrCmp $R5 $R1 found
        StrCmp $R5 "" done
        IntOp $R3 $R3 + 1
        Goto loop
      found:
        StrCpy $R6 $R0 $R3
        IntOp $R3 $R3 + $R4
        StrCpy $R0 $R0 "" $R3
        StrCpy $R0 $R6$R2$R0
        StrCpy $R3 0
        StrLen $R4 $R1
        StrCmp $R4 0 done
        Goto loop
      done:
        Pop $R6
        Pop $R5
        Pop $R4
        Pop $R3
        Push $R0
        Pop $R0
        Exch 2
        Pop $R2
        Pop $R1
        Pop $R0
        Push $R0
      FunctionEnd
      Function un.StrRep
        Exch $R2
        Exch $R1
        Exch 2
        Exch $R0
        Push $R3
        Push $R4
        Push $R5
        Push $R6
        StrCpy $R3 0
        StrLen $R4 $R1
        loop_u:
          StrCpy $R5 $R0 $R4 $R3
          StrCmp $R5 $R1 found_u
          StrCmp $R5 "" done_u
          IntOp $R3 $R3 + 1
          Goto loop_u
        found_u:
          StrCpy $R6 $R0 $R3
          IntOp $R3 $R3 + $R4
          StrCpy $R0 $R0 "" $R3
          StrCpy $R0 $R6$R2$R0
          StrCpy $R3 0
          StrLen $R4 $R1
          StrCmp $R4 0 done_u
          Goto loop_u
        done_u:
          Pop $R6
          Pop $R5
          Pop $R4
          Pop $R3
          Push $R0
          Pop $R0
          Exch 2
          Pop $R2
          Pop $R1
          Pop $R0
          Push $R0
        FunctionEnd

!macro _RemoveFromPathImpl
Function un.RemoveFromPath
  Exch $0
  Push $1
  Push $2
  ReadRegStr $1 HKCU "Environment" "Path"
  Push "$1;"
  Push ";$0;"
  Call un.StrContains
  Pop $2
  StrCmp $2 "" done
    !insertmacro StrRep $1 "$1;" ";$0;" ";"
    WriteRegExpandStr HKCU "Environment" "Path" "$1"
    SendMessage ${HWND_BROADCAST} ${WM_WININICHANGE} 0 "STR:Environment" /TIMEOUT=2000
  done:
    Pop $2
    Pop $1
    Pop $0
FunctionEnd
!macroend
!insertmacro _RemoveFromPathImpl

Function StrContains
  Exch $1 ; needle
  Exch
  Exch $0 ; haystack
  Exch
  Push $2
  Push $3
  StrCpy $2 -1
  IntOp $2 $2 + 1
  StrCpy $3 $0 1 $2
  StrCmp $3 "" notfound
  StrCpy $3 $0 ${NSIS_MAX_STRLEN} $2
  StrCmp $3 $1 found
  Goto -4
  found:
    StrCpy $2 $2 $0 ""
    StrCpy $0 $2
    Goto done
  notfound:
    StrCpy $0 ""
  done:
    Pop $3
    Pop $2
    Exch $0
    Pop $1
FunctionEnd

Function un.StrContains
  Exch $1
  Exch
  Exch $0
  Exch
  Push $2
  Push $3
  StrCpy $2 -1
  IntOp $2 $2 + 1
  StrCpy $3 $0 1 $2
  StrCmp $3 "" notfound
  StrCpy $3 $0 ${NSIS_MAX_STRLEN} $2
  StrCmp $3 $1 found
  Goto -4
  found:
    StrCpy $2 $2 $0 ""
    StrCpy $0 $2
    Goto done
  notfound:
    StrCpy $0 ""
  done:
    Pop $3
    Pop $2
    Exch $0
    Pop $1
FunctionEnd


