using ClipRoo.Core.Protocol;

namespace ClipRoo.Core.Devices;

/// <param name="TokenHash">SHA-256 of the phone's token: the token itself is never kept.</param>
public sealed record Device(string PhoneId, string Name, string Platform, string AppVersion, string TokenHash,
    DateTime Paired, DateTime? LastSeen);

/// <summary>The paired phones (devices.json).</summary>
public sealed class DeviceStore
{
    private const string FileName = "devices.json";
    private static readonly TimeSpan SaveLastSeenEvery = TimeSpan.FromMinutes(5);
    private readonly string _path;
    private readonly TimeProvider _time;
    private readonly Lock _lock = new();
    private readonly Dictionary<string, Device> _byId;
    private readonly Dictionary<string, string> _idByHash;
    private DateTimeOffset _lastSaved;

    /// <summary>A phone was paired, removed or renamed.</summary>
    public event Action? Changed;

    public DeviceStore(string dataFolder, TimeProvider time)
    {
        _path = Path.Combine(dataFolder, FileName);
        _time = time;
        var saved = JsonFile.Read<List<Device>>(_path) ?? [];
        _byId = saved.ToDictionary(d => d.PhoneId);
        _idByHash = saved.ToDictionary(d => d.TokenHash, d => d.PhoneId);
    }

    public IReadOnlyList<Device> All
    {
        get { lock (_lock) return [.. _byId.Values.OrderBy(d => d.Paired)]; }
    }

    /// <summary>Pairs a phone (again) and returns its new token.</summary>
    public string Pair(string phoneId, string name, string platform, string appVersion)
    {
        var token = Ids.New(32);
        lock (_lock)
        {
            if (_byId.Remove(phoneId, out var old)) _idByHash.Remove(old.TokenHash);
            var device = new Device(phoneId, name, platform, appVersion, Ids.Hash(token), Now(), null);
            _byId[phoneId] = device;
            _idByHash[device.TokenHash] = phoneId;
            Save();
        }
        Changed?.Invoke();
        return token;
    }

    /// <summary>The phone this token belongs to, or null.</summary>
    public Device? Verify(string? token)
    {
        if (string.IsNullOrEmpty(token)) return null;
        var hash = Ids.Hash(token);
        lock (_lock)
        {
            if (!_idByHash.TryGetValue(hash, out var id)) return null;
            var device = _byId[id] with { LastSeen = Now() };
            _byId[id] = device;
            if (_time.GetUtcNow() - _lastSaved > SaveLastSeenEvery) Save();
            return device;
        }
    }

    public bool Remove(string phoneId)
    {
        lock (_lock)
        {
            if (!_byId.Remove(phoneId, out var old)) return false;
            _idByHash.Remove(old.TokenHash);
            Save();
        }
        Changed?.Invoke();
        return true;
    }

    private DateTime Now() => DateTime.SpecifyKind(_time.GetUtcNow().UtcDateTime, DateTimeKind.Utc);

    private void Save()
    {
        JsonFile.Write(_path, _byId.Values.ToList());
        _lastSaved = _time.GetUtcNow();
    }
}
