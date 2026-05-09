using System;
using System.Text;

public static class CryptoTrace
{
    public static bool Enabled = true;

    public static event Action<string> OnTrace;

    public static void Clear()
    {
        if (!Enabled) return;
        OnTrace?.Invoke("__CLEAR__");
    }

    public static void Log(string title, string content = "")
    {
        if (!Enabled) return;

        if (string.IsNullOrEmpty(content))
        {
            OnTrace?.Invoke($"[{title}]");
        }
        else
        {
            OnTrace?.Invoke($"[{title}]\n{content}");
        }
    }

    public static string Hex(byte[] data, int maxBytes = 80)
    {
        if (data == null)
            return "null";

        int count = Math.Min(data.Length, maxBytes);
        StringBuilder sb = new StringBuilder();

        for (int i = 0; i < count; i++)
        {
            sb.Append(data[i].ToString("X2"));
        }

        if (data.Length > maxBytes)
        {
            sb.Append($"... ({data.Length} bytes)");
        }

        return sb.ToString();
    }

    public static string Utf8(byte[] data, int maxChars = 1000)
    {
        if (data == null)
            return "null";

        string text = Encoding.UTF8.GetString(data);

        if (text.Length > maxChars)
            return text.Substring(0, maxChars) + "...";

        return text;
    }

    public static string Mask(string value, int head = 18, int tail = 12)
    {
        if (string.IsNullOrEmpty(value))
            return "";

        if (value.Length <= head + tail)
            return value;

        return value.Substring(0, head) + "..." + value.Substring(value.Length - tail);
    }

    public static string BytesInfo(byte[] data)
    {
        if (data == null)
            return "null";

        return $"{data.Length} bytes\nHEX={Hex(data)}";
    }
}