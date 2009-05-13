
smart-update: smart-update.c
	$(CC) $(CFLAGS) -Wall $< -o $@

install:
	install -m 4755 smart-update /usr/bin/smart-update

uninstall:
	rm -f /usr/bin/smart-update

clean:
	rm -f smart-update
