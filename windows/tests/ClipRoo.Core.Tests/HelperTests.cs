using System.Net;
using ClipRoo.Core.Items;
using ClipRoo.Core.Platform;
using ClipRoo.Core.Server;
using Xunit;

namespace ClipRoo.Core.Tests;

public class HelperTests
{
    [Theory]
    [InlineData("photo.jpg", "photo.jpg")]
    [InlineData("../../evil.exe", "evil.exe")]
    [InlineData("C:\\Windows\\system32\\x.dll", "x.dll")]
    [InlineData("what?<>|*\".txt", "what.txt")]
    [InlineData("CON.txt", "_CON.txt")]
    [InlineData("nul", "_nul")]
    [InlineData("trailing dots...", "trailing dots")]
    [InlineData("   ", "fallback")]
    [InlineData("..", "fallback")]
    [InlineData("tab\there", "tabhere")]
    public void Clean_file_names(string given, string expected) => Assert.Equal(expected, FileNames.Clean(given, "fallback"));

    [Fact]
    public void Long_names_keep_their_extension()
    {
        var name = FileNames.Clean(new string('a', 300) + ".pdf", "x");
        Assert.Equal(150, name.Length);
        Assert.EndsWith(".pdf", name);
    }

    [Fact]
    public void Unique_names_never_overwrite()
    {
        var folder = Directory.CreateTempSubdirectory("cliproo-names-").FullName;
        try
        {
            Assert.Equal(Path.Combine(folder, "a.txt"), FileNames.Unique(folder, "a.txt"));
            File.WriteAllText(Path.Combine(folder, "a.txt"), "");
            File.WriteAllText(Path.Combine(folder, "a (2).txt"), "");
            Assert.Equal(Path.Combine(folder, "a (3).txt"), FileNames.Unique(folder, "a.txt"));
        }
        finally
        {
            Directory.Delete(folder, true);
        }
    }

    [Fact]
    public void Picture_formats_by_their_first_bytes()
    {
        Assert.Equal(PictureFormat.Jpeg, PictureFormats.Detect([0xFF, 0xD8, 0xFF, 0xE1]));
        Assert.Equal(PictureFormat.Png, PictureFormats.Detect([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0]));
        Assert.Equal(PictureFormat.Gif, PictureFormats.Detect("GIF89a.."u8));
        Assert.Equal(PictureFormat.WebP, PictureFormats.Detect("RIFF\0\0\0\0WEBPVP8 "u8));
        byte[] bmp = [(byte)'B', (byte)'M', 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 40, 0, 0, 0];
        Assert.Equal(PictureFormat.Bmp, PictureFormats.Detect(bmp));
        Assert.Equal(PictureFormat.Unknown, PictureFormats.Detect("BMW is a car brand"u8));
        Assert.Equal(PictureFormat.Heic, PictureFormats.Detect("\0\0\0\u0018ftypheic"u8));
        Assert.Equal(PictureFormat.Unknown, PictureFormats.Detect("{\"text\": 1}"u8));
    }

    [Fact]
    public void Addresses_for_pairing()
    {
        Assert.True(Addresses.IsPrivate(IPAddress.Parse("192.168.1.5")));
        Assert.True(Addresses.IsPrivate(IPAddress.Parse("10.0.0.2")));
        Assert.True(Addresses.IsPrivate(IPAddress.Parse("172.20.1.1")));
        Assert.False(Addresses.IsPrivate(IPAddress.Parse("172.32.0.1")));
        Assert.False(Addresses.IsPrivate(IPAddress.Parse("8.8.8.8")));
        Assert.Equal("desktop-7gh2k1l.local", Addresses.LocalName("DESKTOP-7GH2K1L"));
        Assert.Null(Addresses.LocalName("bad_name"));
        Assert.All(Addresses.Candidates(47820, "TESTPC"), a => Assert.EndsWith(":47820", a));
    }
}
