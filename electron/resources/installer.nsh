; ogenti — Silent installer with process cleanup
!macro customInit
  ; Kill running ogenti processes before install/uninstall
  nsExec::ExecToLog 'taskkill /F /IM ogenti.exe /T'
  Sleep 1000
!macroend

!macro preInit
  SetSilent silent
!macroend
