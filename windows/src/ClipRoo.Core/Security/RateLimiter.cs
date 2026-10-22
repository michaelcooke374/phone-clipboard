namespace ClipRoo.Core.Security;

/// <summary>At most <c>limit</c> tries per address per minute; after that the address waits
/// until its minute is over.</summary>
public sealed class RateLimiter(int limit, TimeProvider time)
{
    private static readonly TimeSpan Window = TimeSpan.FromMinutes(1);
    private readonly Dictionary<string, (int Count, DateTimeOffset Start)> _tries = [];
    private readonly Lock _lock = new();

    public bool IsBlocked(string address)
    {
        lock (_lock)
        {
            return _tries.TryGetValue(address, out var t) && time.GetUtcNow() - t.Start < Window && t.Count >= limit;
        }
    }

    public void Count(string address)
    {
        lock (_lock)
        {
            var now = time.GetUtcNow();
            if (_tries.TryGetValue(address, out var t) && now - t.Start < Window)
                _tries[address] = (t.Count + 1, t.Start);
            else
                _tries[address] = (1, now);
            if (_tries.Count > 1000)                    // forget old addresses
                foreach (var old in _tries.Where(p => now - p.Value.Start >= Window).Select(p => p.Key).ToList())
                    _tries.Remove(old);
        }
    }
}
