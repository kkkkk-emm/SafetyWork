using System;
using System.Text;

public enum CryptoTraceFlow
{
    None,
    RsaEncrypt,
    DesEncrypt,
    DesDecrypt
}

public struct CryptoTraceStep
{
    public CryptoTraceFlow flow;
    public int stepIndex;
    public int stepCount;
    public string title;
    public string summary;
    public string input;
    public string output;
    public string formula;
}

public static class CryptoTrace
{
    public static bool Enabled = true;

    public static event Action OnClear;
    public static event Action<CryptoTraceStep> OnStep;
    public static event Action<string> OnLog;

    public static void Clear()
    {
        if (!Enabled) return;
        OnClear?.Invoke();
    }

    public static void Step(
        CryptoTraceFlow flow,
        int stepIndex,
        int stepCount,
        string title,
        string summary,
        string input = "",
        string output = "",
        string formula = ""
    )
    {
        if (!Enabled) return;

        OnStep?.Invoke(new CryptoTraceStep
        {
            flow = flow,
            stepIndex = stepIndex,
            stepCount = stepCount,
            title = title,
            summary = summary,
            input = input,
            output = output,
            formula = formula
        });
    }

    public static void Log(string title, string content = "")
    {
        if (!Enabled) return;

        if (string.IsNullOrEmpty(content))
            OnLog?.Invoke($"[{title}]");
        else
            OnLog?.Invoke($"[{title}]\n{content}");
    }

    public static string FlowName(CryptoTraceFlow flow)
    {
        switch (flow)
        {
            case CryptoTraceFlow.RsaEncrypt:
                return "RSA 加密流程";
            case CryptoTraceFlow.DesEncrypt:
                return "DES 加密流程";
            case CryptoTraceFlow.DesDecrypt:
                return "DES 解密流程";
            default:
                return "加密过程可视化";
        }
    }

    public static string Hex(byte[] data, int maxBytes = 48)
    {
        if (data == null)
            return "null";

        int count = Math.Min(data.Length, maxBytes);
        StringBuilder sb = new StringBuilder();

        for (int i = 0; i < count; i++)
            sb.Append(data[i].ToString("X2"));

        if (data.Length > maxBytes)
            sb.Append($"... ({data.Length} bytes)");

        return sb.ToString();
    }

    public static string BytesInfo(byte[] data, int maxBytes = 48)
    {
        if (data == null)
            return "null";

        return $"{data.Length} bytes\n{Hex(data, maxBytes)}";
    }

    public static string Mask(string value, int head = 32, int tail = 16)
    {
        if (string.IsNullOrEmpty(value))
            return "";

        if (value.Length <= head + tail)
            return value;

        return value.Substring(0, head) + "..." + value.Substring(value.Length - tail);
    }
}