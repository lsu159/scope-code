# Scope Code Demo
# Record with: vhs demo.tape
# Install vhs: https://github.com/charmbracelet/vhs

Set FontSize 16
Set Width 80
Set Height 30
Set Padding 2
Set Theme "Dark"

Hide

Type "export SCOPE_CODE_API_KEY=sk-xxx"
Sleep 100ms
Enter
Type "clear"
Sleep 100ms
Enter

Show

Type "python demo_gif.py"
Sleep 500ms
Enter

Sleep 8s

# Done — vhs will auto-stop here
