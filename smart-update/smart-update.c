/*

 Copyright (c) 2004 Conectiva, Inc.

 Written by Gustavo Niemeyer <niemeyer@conectiva.com>

 This file is part of Smart Package Manager.

 Smart Package Manager is free software; you can redistribute it and/or
 modify it under the terms of the GNU General Public License as published
 by the Free Software Foundation; either version 2 of the License, or (at
 your option) any later version.

 Smart Package Manager is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
 General Public License for more details.

 You should have received a copy of the GNU General Public License
 along with Smart Package Manager; if not, write to the Free Software
 Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

*/
#define _GNU_SOURCE
#include <sys/resource.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <grp.h>
#include <unistd.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <stdio.h>
#include <pwd.h>

inline int min(int a, int b)
{
  return a < b ? a : b;
}

int main(int argc, char *argv[], char *envp[])
{
    char *smart_argv[] = {"/usr/share/smart/smart", "update", NULL, NULL};
    char *smart_envp[] = {"PATH=/bin:/usr/bin", NULL, NULL};

    // Set the HOME environment variable
    struct passwd *pwd = getpwuid(geteuid());
    if (!pwd) {
        fprintf(stderr, "error: Unable to find passwd entry for uid %d (%s)\n",
                geteuid(), strerror(errno));
        exit(1);
    }
    if (asprintf(&smart_envp[1], "HOME=%s", pwd->pw_dir) == -1) {
        fprintf(stderr, "error: Unable to create HOME environment variable (%s)\n",
                strerror(errno));
        exit(1);
    }

    // Handle the --after command line option
    if (argc != 1) {
        if (argc != 3 || strcmp(argv[1], "--after") != 0) {
          fprintf(stderr, "error: Unsupported command line option\n");
          exit(1);
        }
        char *end;
        long interval = strtol(argv[2], &end, 10);
        if (interval == 0) {
          fprintf(stderr, "error: Wrong interval value '%s'\n", argv[2]);
          exit(1);
        }
        if (asprintf(&smart_argv[2], "--after=%ld", interval) == -1) {
          fprintf(stderr, "error: Unable to create argument variable (%s)\n",
                  strerror(errno));
          exit(1);
        }
    }

    // Set real/effective gid and uid
    if (setregid(pwd->pw_gid, pwd->pw_gid) == -1) {
        fprintf(stderr, "error: Unable to set real and effective gid (%s)\n",
                strerror(errno));
        exit(1);
    }
    if (setreuid(pwd->pw_uid, pwd->pw_uid) == -1) {
        fprintf(stderr, "error: Unable to set real and effective uid (%s)\n",
                strerror(errno));
        exit(1);
    }

    // Drop any supplementary group
    if (setgroups(0, NULL) == -1) {
        fprintf(stderr, "error: Unable to set supplementary groups IDs (%s)\n",
                strerror(errno));
        exit(1);
    }

    // Close all file descriptors except the standard ones
    struct rlimit rlp;
    if (getrlimit(RLIMIT_NOFILE, &rlp) == -1) {
        fprintf(stderr, "error: Unable to determine file descriptor limits (%s)\n",
                strerror(errno));
        exit(1);
    }
    int fd;
    for (fd = 3; fd < min(4096, rlp.rlim_max); fd++) {
      close(fd);
    }

    // Set umask to 022
    umask(S_IWGRP | S_IWOTH);

    // Change working directory to "/tmp"
    if (chdir("/") == -1) {
        fprintf(stderr, "error: Unable change working directory (%s)\n",
                strerror(errno));
        exit(1);
    }

    // Run smart update
    execve(smart_argv[0], smart_argv, smart_envp);
    perror("error: Unable to execute smart");
    return 1;
}

/* vim:ts=4:sw=4:et
*/
