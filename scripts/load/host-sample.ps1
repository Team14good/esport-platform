# 輸出一行「主機整機 CPU%,可用記憶體 MB」，由 run.sh 每隔幾秒呼叫一次（run.sh 為每筆加上時間）。
# 可用記憶體是 Available MBytes（含待命快取，等同工作管理員的「可用」），不是 FreePhysicalMemory（只算完全閒置的頁面）。
$cpu = (Get-CimInstance Win32_PerfFormattedData_PerfOS_Processor | Select-Object -Last 1).PercentProcessorTime  # 最後一列是 _Total
$mem = (Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory).AvailableMBytes
"$cpu,$mem"
