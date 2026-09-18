' Chay mot job cua scripts/sched.sh qua Git Bash, KHONG hien cua so console.
'
' Chi danh cho Windows Task Scheduler tren may dev. Ubuntu goi thang
' scripts/sched.sh trong cron, khong can file nay.
'
' Ly do ton tai: task chay voi LogonType=Interactive nen Windows cap console
' cho bash.exe — cua so nhay len moi 5 phut suot gio giao dich. Cach sach hon
' la doi principal sang S4U, nhung viec do CAN QUYEN ADMIN. Day la duong vong
' khong can elevated.
'
' Dung: wscript.exe //B //Nologo run_hidden.vbs <job>
'   voi <job> = heartbeat | daily-check | backfill | deploy-drift | engine-cam | engine-consumer | stream-health

Option Explicit

Dim sh, fso, job, repo, cmd, rc

If WScript.Arguments.Count <> 1 Then
  WScript.Quit 2
End If
job = WScript.Arguments(0)

Set fso = CreateObject("Scripting.FileSystemObject")
' Thu muc repo = cha cua scripts/
repo = fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName))

Set sh = CreateObject("WScript.Shell")

' Doi D:\path thanh /d/path cho Git Bash.
Dim posix
posix = "/" & LCase(Left(repo, 1)) & Replace(Mid(repo, 3), "\", "/")

cmd = """C:\Program Files\Git\bin\bash.exe"" -lc """ & posix & "/scripts/sched.sh " & job & """"

' 0 = cua so an. True = cho chay xong, de Task Scheduler biet thoi luong that
' va khong chong lan lan chay ke tiep.
rc = sh.Run(cmd, 0, True)
WScript.Quit rc
