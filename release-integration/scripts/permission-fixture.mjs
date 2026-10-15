// B0's immutable test intentionally creates a 0644 unsafe descriptor. The shared
// lock's inherited 0077 umask otherwise changes that fixture into a safe 0600 file.
// Set the ordinary fixture umask only in the test process, never in the launcher.
process.umask(0o022);
