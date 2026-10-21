using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Interop;
using System.Windows.Media;

namespace PixelSnowOverlay;

public partial class MainWindow : Window
{
    private const int GwlExStyle = -20;
    private const int WsExTransparent = 0x00000020;
    private const int WsExLayered = 0x00080000;
    private const int WsExToolWindow = 0x00000080;
    private const int WmHotkey = 0x0312;
    private const int HotkeyId = 0x51A7;
    private const uint ModControl = 0x0002;
    private const uint ModShift = 0x0004;
    private const uint VkF12 = 0x7B;

    private readonly List<Flake> _flakes = new();
    private readonly Random _random = new();
    private HwndSource? _source;
    private bool _hotkeyRegistered;
    private DateTime _lastFrame;

    public MainWindow()
    {
        InitializeComponent();
        Left = SystemParameters.VirtualScreenLeft;
        Top = SystemParameters.VirtualScreenTop;
        Width = SystemParameters.VirtualScreenWidth;
        Height = SystemParameters.VirtualScreenHeight;
        Loaded += OnLoaded;
        Closed += OnClosed;
        CompositionTarget.Rendering += OnRendering;
    }

    private void OnLoaded(object sender, RoutedEventArgs e)
    {
        var hwnd = new WindowInteropHelper(this).Handle;
        var style = GetWindowLongPtr(hwnd, GwlExStyle).ToInt64();
        SetWindowLongPtr(hwnd, GwlExStyle, new IntPtr(style | WsExTransparent | WsExLayered | WsExToolWindow));

        _source = HwndSource.FromHwnd(hwnd);
        _source?.AddHook(WndProc);
        _hotkeyRegistered = RegisterHotKey(hwnd, HotkeyId, ModControl | ModShift, VkF12);

        var area = Math.Max(1, ActualWidth * ActualHeight);
        var count = Math.Clamp((int)(area / 18000), 90, 360);
        for (var i = 0; i < count; i++)
            _flakes.Add(CreateFlake(randomY: true));
    }

    private Flake CreateFlake(bool randomY)
    {
        var size = _random.Next(2, 6);
        return new Flake
        {
            X = _random.NextDouble() * Math.Max(1, ActualWidth),
            Y = randomY ? _random.NextDouble() * Math.Max(1, ActualHeight) : -10,
            Size = size,
            Speed = 22 + _random.NextDouble() * 72,
            Drift = (_random.NextDouble() - 0.5) * 24,
            Phase = _random.NextDouble() * Math.PI * 2,
            Rotation = _random.NextDouble() * Math.PI,
            Spin = (_random.NextDouble() - 0.5) * 1.2,
            Opacity = 0.38 + _random.NextDouble() * 0.58
        };
    }

    private void OnRendering(object? sender, EventArgs e)
    {
        if (!IsLoaded || _flakes.Count == 0) return;
        var now = DateTime.UtcNow;
        if (_lastFrame == default) _lastFrame = now;
        var dt = Math.Clamp((now - _lastFrame).TotalSeconds, 0, 0.05);
        _lastFrame = now;

        foreach (var flake in _flakes)
        {
            flake.Y += flake.Speed * dt;
            flake.X += (flake.Drift + Math.Sin(flake.Y / 85 + flake.Phase) * 10) * dt;
            flake.Rotation += flake.Spin * dt;
            if (flake.Y > ActualHeight + 12 || flake.X < -20 || flake.X > ActualWidth + 20)
            {
                var replacement = CreateFlake(false);
                flake.X = replacement.X;
                flake.Y = replacement.Y;
                flake.Size = replacement.Size;
                flake.Speed = replacement.Speed;
                flake.Drift = replacement.Drift;
                flake.Phase = replacement.Phase;
                flake.Rotation = replacement.Rotation;
                flake.Spin = replacement.Spin;
                flake.Opacity = replacement.Opacity;
            }
        }
        InvalidateVisual();
    }

    protected override void OnRender(DrawingContext dc)
    {
        base.OnRender(dc);
        foreach (var f in _flakes)
        {
            var s = f.Size;
            var brush = new SolidColorBrush(Color.FromArgb((byte)(255 * f.Opacity), 238, 247, 255));
            brush.Freeze();
            dc.PushTransform(new TranslateTransform(f.X, f.Y));
            dc.PushTransform(new RotateTransform(f.Rotation * 180 / Math.PI));
            // Chunky 8-bit snowflake silhouette.
            dc.DrawRectangle(brush, null, new Rect(-s / 2, -s * 1.5, s, s * 3));
            dc.DrawRectangle(brush, null, new Rect(-s * 1.5, -s / 2, s * 3, s));
            dc.DrawRectangle(brush, null, new Rect(-s, -s, s, s));
            dc.DrawRectangle(brush, null, new Rect(0, -s, s, s));
            dc.DrawRectangle(brush, null, new Rect(-s, 0, s, s));
            dc.DrawRectangle(brush, null, new Rect(0, 0, s, s));
            dc.Pop();
            dc.Pop();
        }
    }

    private IntPtr WndProc(IntPtr hwnd, int msg, IntPtr wParam, IntPtr lParam, ref bool handled)
    {
        if (msg == WmHotkey && wParam.ToInt32() == HotkeyId)
        {
            handled = true;
            Close();
        }
        return IntPtr.Zero;
    }

    private void OnClosed(object? sender, EventArgs e)
    {
        CompositionTarget.Rendering -= OnRendering;
        var hwnd = new WindowInteropHelper(this).Handle;
        if (_hotkeyRegistered) UnregisterHotKey(hwnd, HotkeyId);
        _source?.RemoveHook(WndProc);
    }

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool RegisterHotKey(IntPtr hWnd, int id, uint fsModifiers, uint vk);
    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool UnregisterHotKey(IntPtr hWnd, int id);
    [DllImport("user32.dll", EntryPoint = "GetWindowLongPtrW", SetLastError = true)]
    private static extern IntPtr GetWindowLongPtr(IntPtr hWnd, int nIndex);
    [DllImport("user32.dll", EntryPoint = "SetWindowLongPtrW", SetLastError = true)]
    private static extern IntPtr SetWindowLongPtr(IntPtr hWnd, int nIndex, IntPtr dwNewLong);

    private sealed class Flake
    {
        public double X, Y, Size, Speed, Drift, Phase, Rotation, Spin, Opacity;
    }
}
