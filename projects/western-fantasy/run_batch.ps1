$env:PYTHONIOENCODING = "utf-8"
$env:HF_ENDPOINT = "https://hf-mirror.com"
$logFile = "e:\Test\xiaoshuo\projects\western-fantasy\batch_write.log"
"Starting batch rewrite for Ch 61-62 (Mirror Enabled)..." | Out-File -Encoding utf8 $logFile
python auto_write.py 61 62 >> $logFile 2>&1
"Batch rewrite completed." >> $logFile
