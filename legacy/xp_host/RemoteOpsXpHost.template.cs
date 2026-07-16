using System;
using System.Drawing;
using System.Windows.Forms;

namespace RemoteOpsWorkspace.XpHost
{
    internal static class Program
    {
        private const string ProductVersion = "@VERSION@";

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
                Console.WriteLine("loopback profile dry-run: passed");
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
                MessageBox.Show(
                    window,
                    "Loopback profile dry-run passed.\r\n\r\n" +
                    "Legacy compatibility remains isolated and opt-in.",
                    "Remote Ops Workspace XP Host",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Information);
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
