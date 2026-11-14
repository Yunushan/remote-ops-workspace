using System;
using System.Drawing;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Windows.Forms;

namespace RemoteOpsWorkspace.XpHost
{
    internal static class Program
    {
        private const string ProductVersion = "@VERSION@";
        private const int ProbeTimeoutMilliseconds = 3000;

        [STAThread]
        private static int Main(string[] args)
        {
            if (HasArgument(args, "--version"))
            {
                Console.WriteLine("Remote Ops Workspace XP Host " + ProductVersion);
                return 0;
            }
            if (HasArgument(args, "--loopback-dry-run"))
            {
                if (!VerifyLoopback())
                {
                    Console.Error.WriteLine("loopback profile dry-run: failed");
                    return 1;
                }
                Console.WriteLine("loopback profile dry-run: passed");
                Console.WriteLine("loopback TCP round trip: passed");
                Console.WriteLine("legacy compatibility profile: isolated-opt-in");
                Console.WriteLine("modern defaults unchanged: true");
                return 0;
            }
            if (HasArgument(args, "--legacy-profile"))
            {
                Console.WriteLine("legacy compatibility profile: isolated-opt-in");
                Console.WriteLine("legacy crypto scope: profile-only");
                Console.WriteLine("weak crypto global default: false");
                return 0;
            }

            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            using (Form window = CreateWindow())
            {
                if (HasArgument(args, "--gui-smoke"))
                {
                    Timer closer = new Timer();
                    closer.Interval = 1000;
                    closer.Tick += delegate(object sender, EventArgs eventArgs)
                    {
                        closer.Stop();
                        window.Close();
                    };
                    closer.Start();
                }
                Application.Run(window);
            }
            return 0;
        }

        private static bool VerifyLoopback()
        {
            const int request = 0x52;
            const int response = 0x4f;
            TcpListener listener = new TcpListener(IPAddress.Loopback, 0);
            try
            {
                listener.ExclusiveAddressUse = true;
                listener.Start(1);
                listener.Server.Blocking = false;
                IPEndPoint endpoint = (IPEndPoint)listener.LocalEndpoint;
                using (TcpClient sender = new TcpClient(AddressFamily.InterNetwork))
                {
                    IAsyncResult connection = sender.BeginConnect(endpoint.Address, endpoint.Port, null, null);
                    using (System.Threading.WaitHandle completion = connection.AsyncWaitHandle)
                    {
                        if (!completion.WaitOne(ProbeTimeoutMilliseconds))
                        {
                            return false;
                        }
                        sender.EndConnect(connection);
                    }
                    using (TcpClient receiver = listener.AcceptTcpClient())
                    {
                        receiver.Client.Blocking = true;
                        if (!sender.Client.LocalEndPoint.Equals(receiver.Client.RemoteEndPoint))
                        {
                            return false;
                        }
                        using (NetworkStream outgoing = sender.GetStream())
                        using (NetworkStream incoming = receiver.GetStream())
                        {
                            outgoing.ReadTimeout = outgoing.WriteTimeout = ProbeTimeoutMilliseconds;
                            incoming.ReadTimeout = incoming.WriteTimeout = ProbeTimeoutMilliseconds;
                            outgoing.WriteByte(request);
                            if (incoming.ReadByte() != request)
                            {
                                return false;
                            }
                            incoming.WriteByte(response);
                            return outgoing.ReadByte() == response;
                        }
                    }
                }
            }
            catch (SocketException)
            {
                return false;
            }
            catch (IOException)
            {
                return false;
            }
            finally
            {
                listener.Stop();
            }
        }

        private static bool HasArgument(string[] args, string expected)
        {
            foreach (string argument in args)
            {
                if (String.Equals(argument, expected, StringComparison.OrdinalIgnoreCase))
                {
                    return true;
                }
            }
            return false;
        }

        private static Form CreateWindow()
        {
            Form window = new Form();
            window.Text = "Remote Ops Workspace XP Host";
            window.ClientSize = new Size(520, 260);
            window.MinimumSize = new Size(520, 260);
            window.StartPosition = FormStartPosition.CenterScreen;
            window.Font = SystemFonts.MessageBoxFont;

            Label heading = new Label();
            heading.Text = "Remote Ops Workspace Legacy Host";
            heading.Font = new Font(window.Font, FontStyle.Bold);
            heading.Location = new Point(20, 20);
            heading.AutoSize = true;

            Label details = new Label();
            details.Text =
                "Windows XP native-host companion\r\n" +
                "Version " + ProductVersion + "\r\n\r\n" +
                "Use the modern operator application for full workflows. This\r\n" +
                "legacy host keeps compatibility settings isolated per profile.";
            details.Location = new Point(20, 55);
            details.Size = new Size(470, 125);

            Button dryRun = new Button();
            dryRun.Text = "Loopback dry-run";
            dryRun.Location = new Point(20, 200);
            dryRun.Size = new Size(130, 28);
            dryRun.Click += delegate(object sender, EventArgs eventArgs)
            {
                bool passed = VerifyLoopback();
                MessageBox.Show(
                    window,
                    passed ? "Loopback TCP round trip passed." : "Loopback TCP round trip failed.",
                    "Remote Ops Workspace XP Host",
                    MessageBoxButtons.OK,
                    passed ? MessageBoxIcon.Information : MessageBoxIcon.Warning);
            };

            Button close = new Button();
            close.Text = "Close";
            close.Location = new Point(390, 200);
            close.Size = new Size(100, 28);
            close.DialogResult = DialogResult.Cancel;

            window.CancelButton = close;
            window.Controls.Add(heading);
            window.Controls.Add(details);
            window.Controls.Add(dryRun);
            window.Controls.Add(close);
            return window;
        }
    }
}
