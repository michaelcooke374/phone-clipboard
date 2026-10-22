using System.Text;
using ClipRoo.Core.Protocol;

namespace ClipRoo.Core.Items;

/// <summary>An item as the bridge keeps it: the item the phone sees, plus where its content is.</summary>
public sealed record StoredItem
{
    public required Item Item { get; init; }

    /// <summary>The whole text of a text item (the item itself leaves out texts over 64 KB).</summary>
    public string? FullText { get; init; }

    /// <summary>The picture or files on this PC.</summary>
    public IReadOnlyList<string> Paths { get; init; } = [];

    /// <summary>A copied picture's bytes (current clipboard only: never saved).</summary>
    public byte[]? Data { get; init; }
}

/// <summary>History (both directions) and the outbox (things sent to the phone on purpose).</summary>
public sealed class ItemStore
{
    public const int MaxInlineTextBytes = 64 * 1024;
    private const int MaxHistory = 500;
    private static readonly TimeSpan KeepHistory = TimeSpan.FromDays(30);
    private static readonly TimeSpan KeepOutbox = TimeSpan.FromDays(7);
    private readonly string _historyPath;
    private readonly string _outboxPath;
    private readonly TimeProvider _time;
    private readonly Lock _lock = new();
    private readonly List<StoredItem> _history;     // newest first
    private readonly List<StoredItem> _outbox;      // oldest first

    public event Action? Changed;

    public ItemStore(string dataFolder, TimeProvider time)
    {
        _historyPath = Path.Combine(dataFolder, "history.json");
        _outboxPath = Path.Combine(dataFolder, "outbox.json");
        _time = time;
        _history = JsonFile.Read<List<StoredItem>>(_historyPath) ?? [];
        _outbox = JsonFile.Read<List<StoredItem>>(_outboxPath) ?? [];
    }

    /// <summary>Now, to the second, in UTC (how items are timed).</summary>
    public DateTime Now()
    {
        var now = _time.GetUtcNow().UtcDateTime;
        return new DateTime(now.Ticks - now.Ticks % TimeSpan.TicksPerSecond, DateTimeKind.Utc);
    }

    public static StoredItem TextItem(string id, string origin, string text, DateTime created)
    {
        var size = Encoding.UTF8.GetByteCount(text);
        return new StoredItem
        {
            Item = new Item
            {
                Id = id, Origin = origin, Kind = Kinds.Text, Created = created, Size = size,
                Text = size <= MaxInlineTextBytes ? text : null,
            },
            FullText = text,
        };
    }

    public void AddHistory(StoredItem item)
    {
        lock (_lock)
        {
            _history.RemoveAll(i => i.Item.Id == item.Item.Id);
            _history.Insert(0, item with { Data = null });
            Trim();
            JsonFile.Write(_historyPath, _history);
        }
        Changed?.Invoke();
    }

    public IReadOnlyList<StoredItem> History(string? before = null, int limit = 50)
    {
        limit = Math.Clamp(limit, 1, 100);
        lock (_lock)
        {
            var start = 0;
            if (before is not null)
            {
                var at = _history.FindIndex(i => i.Item.Id == before);
                if (at < 0) return [];
                start = at + 1;
            }
            return _history.Skip(start).Take(limit).ToList();
        }
    }

    public void AddToOutbox(StoredItem item)
    {
        lock (_lock)
        {
            _outbox.Add(item with { Data = null });
            Trim();
            JsonFile.Write(_outboxPath, _outbox);
        }
        Changed?.Invoke();
    }

    public IReadOnlyList<StoredItem> Outbox()
    {
        lock (_lock)
        {
            Trim();
            return _outbox.ToList();
        }
    }

    /// <summary>The phone has it: it leaves the outbox and joins the history.</summary>
    public bool Done(string id)
    {
        StoredItem? item;
        lock (_lock)
        {
            item = _outbox.Find(i => i.Item.Id == id);
            if (item is null) return false;
            _outbox.Remove(item);
            JsonFile.Write(_outboxPath, _outbox);
        }
        AddHistory(item);
        return true;
    }

    public StoredItem? Find(string id)
    {
        lock (_lock)
        {
            return _history.Find(i => i.Item.Id == id) ?? _outbox.Find(i => i.Item.Id == id);
        }
    }

    private void Trim()
    {
        var now = _time.GetUtcNow().UtcDateTime;
        _history.RemoveAll(i => now - i.Item.Created > KeepHistory);
        if (_history.Count > MaxHistory) _history.RemoveRange(MaxHistory, _history.Count - MaxHistory);
        _outbox.RemoveAll(i => now - i.Item.Created > KeepOutbox);
    }
}
