import tempfile
import shutil
import os

from landscape.lib.persist import Persist
from landscape.broker.store import MessageStore
from landscape.schema import InvalidError, Message, Int, String, UnicodeOrString

from landscape.tests.helpers import LandscapeTest
from landscape.tests.mocker import ANY
from landscape import API


class MessageStoreTest(LandscapeTest):

    def setUp(self):
        super(MessageStoreTest, self).setUp()
        self.time = 0
        self.temp_dir = tempfile.mkdtemp()
        self.persist_filename = tempfile.mktemp()
        self.persist = Persist(filename=self.persist_filename)
        self.store = self.create_store()

    def create_store(self):
        persist = Persist(filename=self.persist_filename)
        store = MessageStore(persist, self.temp_dir, 20, get_time=self.get_time)
        store.set_accepted_types(["empty", "data"])
        store.add_schema(Message("empty", {}))
        store.add_schema(Message("empty2", {}))
        store.add_schema(Message("data", {"data": String()}))
        store.add_schema(Message("unaccepted", {"data": String()}))
        return store

    def tearDown(self):
        super(MessageStoreTest, self).tearDown()
        shutil.rmtree(self.temp_dir)
        if os.path.isfile(self.persist_filename):
            os.unlink(self.persist_filename)

    def get_time(self):
        return self.time

    def test_get_set_sequence(self):
        self.assertEquals(self.store.get_sequence(), 0)
        self.store.set_sequence(3)
        self.assertEquals(self.store.get_sequence(), 3)

        # Ensure it's actually saved.
        self.store.commit()
        store = self.create_store()
        self.assertEquals(store.get_sequence(), 3)

    def test_get_set_server_sequence(self):
        self.assertEquals(self.store.get_server_sequence(), 0)
        self.store.set_server_sequence(3)
        self.assertEquals(self.store.get_server_sequence(), 3)

        # Ensure it's actually saved.
        self.store.commit()
        store = self.create_store()
        self.assertEquals(store.get_server_sequence(), 3)

    def test_get_pending_offset(self):
        self.assertEquals(self.store.get_pending_offset(), 0)
        self.store.set_pending_offset(3)
        self.assertEquals(self.store.get_pending_offset(), 3)

    def test_add_pending_offset(self):
        self.assertEquals(self.store.get_pending_offset(), 0)
        self.store.add_pending_offset(3)
        self.assertEquals(self.store.get_pending_offset(), 3)
        self.store.add_pending_offset(3)
        self.assertEquals(self.store.get_pending_offset(), 6)
        self.store.add_pending_offset(-3)
        self.assertEquals(self.store.get_pending_offset(), 3)

    def test_no_pending_messages(self):
        self.assertEquals(self.store.get_pending_messages(1), [])

    def test_delete_no_messages(self):
        self.store.delete_old_messages()

    def test_delete_old_messages_does_not_delete_held(self):
        """
        Deleting old messages should avoid deleting held messages.
        """
        self.store.add({"type": "unaccepted", "data": "blah"})
        self.store.add({"type": "empty"})
        self.store.set_pending_offset(1)
        self.store.delete_old_messages()
        self.store.set_accepted_types(["empty", "unaccepted"])
        self.store.set_pending_offset(0)
        messages = self.store.get_pending_messages()
        self.assertEquals(len(messages), 1)
        self.assertEquals(messages[0]["type"], "unaccepted")

    def test_delete_all_messages(self):
        """Resetting the message store means removing *ALL* messages."""
        self.store.set_accepted_types(["empty"])
        self.store.add({"type": "unaccepted", "data": "blah"})
        self.store.add({"type": "empty"})
        self.store.add({"type": "unaccepted", "data": "blah"})
        self.store.add({"type": "empty"})
        self.store.set_pending_offset(2)
        self.store.delete_all_messages()
        self.store.set_accepted_types(["empty", "unaccepted"])
        self.assertEquals(self.store.get_pending_offset(), 0)
        self.assertEquals(self.store.get_pending_messages(), [])

    def test_one_message(self):
        self.store.add(dict(type="data", data="A thing"))
        messages = self.store.get_pending_messages(200)
        self.assertMessages(messages,
                            [{"type": "data",
                              "data": "A thing",
                              "api": API}])

    def test_max_pending(self):
        for i in range(10):
            self.store.add(dict(type="data", data=str(i)))
        il = [m["data"] for m in self.store.get_pending_messages(5)]
        self.assertEquals(il, map(str, [0, 1, 2, 3, 4]))

    def test_offset(self):
        self.store.set_pending_offset(5)
        for i in range(15):
            self.store.add(dict(type="data", data=str(i)))
        il = [m["data"] for m in self.store.get_pending_messages(5)]
        self.assertEquals(il, map(str, [5, 6, 7, 8, 9]))

    def test_exercise_multi_dir(self):
        for i in range(35):
            self.store.add(dict(type="data", data=str(i)))
        il = [m["data"] for m in self.store.get_pending_messages(50)]
        self.assertEquals(il, map(str, range(35)))

    def test_wb_clean_up_empty_directories(self):
        for i in range(60):
            self.store.add(dict(type="data", data=str(i)))
        il = [m["data"] for m in self.store.get_pending_messages(60)]
        self.assertEquals(il, map(str, range(60)))
        self.assertEquals(set(os.listdir(self.temp_dir)), set(["0", "1", "2"]))

        self.store.set_pending_offset(60)
        self.store.delete_old_messages()
        self.assertEquals(os.listdir(self.temp_dir), [])

    def test_unaccepted(self):
        for i in range(10):
            self.store.add(dict(type=["data", "unaccepted"][i%2], data=str(i)))
        il = [m["data"] for m in self.store.get_pending_messages(20)]
        self.assertEquals(il, map(str, [0, 2, 4, 6, 8]))

    def test_unaccepted_with_offset(self):
        for i in range(10):
            self.store.add(dict(type=["data", "unaccepted"][i%2], data=str(i)))
        self.store.set_pending_offset(2)
        il = [m["data"] for m in self.store.get_pending_messages(20)]
        self.assertEquals(il, map(str, [4, 6, 8]))

    def test_unaccepted_reaccepted(self):
        for i in range(10):
            self.store.add(dict(type=["data", "unaccepted"][i%2], data=str(i)))
        self.store.set_pending_offset(2)
        il = [m["data"] for m in self.store.get_pending_messages(2)]
        self.store.set_accepted_types(["data", "unaccepted"])
        il = [m["data"] for m in self.store.get_pending_messages(20)]
        self.assertEquals(il, map(str, [4, 6, 8, 1, 3, 5, 7, 9]))

    def test_accepted_unaccepted(self):
        for i in range(10):
            self.store.add(dict(type=["data", "unaccepted"][i%2], data=str(i)))
        # Setting pending offset here means that the first two
        # messages, even though becoming unaccepted now, were already
        # accepted before, so they shouldn't be marked for hold.
        self.store.set_pending_offset(2)
        self.store.set_accepted_types(["unaccepted"])
        il = [m["data"] for m in self.store.get_pending_messages(20)]
        self.assertEquals(il, map(str, [1, 3, 5, 7, 9]))
        self.store.set_accepted_types(["data", "unaccepted"])
        il = [m["data"] for m in self.store.get_pending_messages(20)]
        self.assertEquals(il, map(str, [1, 3, 5, 7, 9, 4, 6, 8]))

    def test_accepted_unaccepted_old(self):
        for i in range(10):
            self.store.add(dict(type=["data", "unaccepted"][i%2], data=str(i)))
        self.store.set_pending_offset(2)
        self.store.set_accepted_types(["unaccepted"])
        il = [m["data"] for m in self.store.get_pending_messages(20)]
        self.assertEquals(il, map(str, [1, 3, 5, 7, 9]))
        # Now, if the server asks us to go back and process
        # previously accepted messages that are now unaccepted,
        # they should be put on hold.
        self.store.set_pending_offset(0)
        il = [m["data"] for m in self.store.get_pending_messages(20)]
        self.assertEquals(il, map(str, [1, 3, 5, 7, 9]))
        # When the server starts accepting them again, these old
        # messages will also be delivered.
        self.store.set_accepted_types(["data", "unaccepted"])
        il = [m["data"] for m in self.store.get_pending_messages(20)]
        self.assertEquals(il, map(str, [1, 3, 5, 7, 9, 0, 2, 4, 6, 8]))

    def test_wb_handle_broken_messages(self):
        self.log_helper.ignore_errors(ValueError)
        self.store.add({"type": "empty"})
        self.store.add({"type": "empty2"})

        filename = os.path.join(self.temp_dir, "0", "0")
        self.assertTrue(os.path.isfile(filename))

        file = open(filename, "w")
        file.write("bpickle will break reading this")
        file.close()

        self.assertEquals(self.store.get_pending_messages(), [])

        # FIXME This is an unfortunate assertion because it relies on
        # a message generated by external code.  As it turns out, this
        # message is different between Python 2.4 and 2.5.  The
        # snippet checked here is the largest common chunk between
        # Python 2.4 and 2.5.  It might be worth making the message
        # store call an event handler when it encounters a broken
        # message and hooking on that for this assertion instead of
        # relying on this fragile check.
        self.assertTrue("invalid literal for int()" in self.logfile.getvalue(),
                        self.logfile.getvalue())

        self.logfile.seek(0)
        self.logfile.truncate()

        # Unholding will also load the message.
        self.store.set_accepted_types([])
        self.store.set_accepted_types(["empty", "empty2"])

        self.assertTrue("invalid literal for int()" in self.logfile.getvalue(),
                        self.logfile.getvalue())

    def test_wb_delete_messages_with_broken(self):
        self.log_helper.ignore_errors(ValueError)
        self.store.add({"type": "data", "data": "1"})
        self.store.add({"type": "data", "data": "2"})

        filename = os.path.join(self.temp_dir, "0", "0")
        self.assertTrue(os.path.isfile(filename))

        file = open(filename, "w")
        file.write("bpickle will break reading this")
        file.close()

        messages = self.store.get_pending_messages()

        self.assertEquals(messages, [{"type": "data", "data": "2",
                                      "api": API}])

        self.store.set_pending_offset(len(messages))

        messages = self.store.get_pending_messages()
        self.store.delete_old_messages()
        self.assertEquals(messages, [])
        self.assertTrue("ValueError" in self.logfile.getvalue())

    def test_atomic_message_writing(self):
        """
        If the server gets unplugged halfway through writing a file,
        the message should not be half-written.
        """
        self.store.add_schema(Message("data", {"data": Int()}))
        self.store.add({"type": "data", "data": 1})
        # We simulate it by creating a fake file which raises halfway through
        # writing a file.
        replaced_file_factory = self.mocker.replace("__builtin__.open",
                                                    passthrough=False)
        replaced_file = replaced_file_factory(ANY, "w")
        replaced_file.write(ANY)
        self.mocker.throw(IOError("Sorry, pal!"))
        self.mocker.replay()
        # This kind of ensures that raising an exception is somewhat
        # similar to unplugging the power -- i.e., we're not relying
        # on special exception-handling in the file-writing code.
        self.assertRaises(IOError, self.store.add, {"type": "data", "data": 2})
        self.mocker.verify()
        self.mocker.reset()
        self.assertEquals(self.store.get_pending_messages(),
                         [{"type": "data", "data": 1, "api": API}])

    def test_api_attribute(self):
        self.assertEquals(self.store.api, API)
        new_api = "New API version!"
        self.store.api = new_api
        self.assertEquals(self.store.api, new_api)

    def test_default_api_on_messages(self):
        self.store.add({"type": "empty"})
        self.assertEquals(self.store.get_pending_messages(),
                          [{"type": "empty", "api": API}])

    def test_custom_api_on_store(self):
        self.store.api = "X.Y"
        self.store.add({"type": "empty"})
        self.assertEquals(self.store.get_pending_messages(),
                          [{"type": "empty", "api": "X.Y"}])

    def test_custom_api_on_messages(self):
        self.store.add({"type": "empty", "api": "X.Y"})
        self.assertEquals(self.store.get_pending_messages(),
                          [{"type": "empty", "api": "X.Y"}])

    def test_coercion(self):
        """
        When adding a message to the mesage store, it should be
        coerced according to the message schema for the type of the
        message.
        """
        self.assertRaises(InvalidError,
                          self.store.add, {"type": "data", "data": 3})


    def test_coercion_ignores_custom_api(self):
        """
        If a custom 'api' key is specified in the message, it should
        not be considered during schema verification.
        """
        self.store.add({"type": "empty", "api": "whatever"})

    def test_message_is_actually_coerced(self):
        """
        The message that eventually gets sent should be the result of
        the coercion.
        """
        self.store.add_schema(
            Message("data", {"data": UnicodeOrString("utf-8")}))
        self.store.add({"type": "data",
                        "data": u"\N{HIRAGANA LETTER A}".encode("utf-8"),
                        "api": "whatever"})
        self.assertEquals(self.store.get_pending_messages(),
                          [{"type": "data", "api": "whatever",
                            "data": u"\N{HIRAGANA LETTER A}"}])

    def test_count_pending_messages(self):
        """It is possible to get the total number of pending messages."""
        self.assertEquals(self.store.count_pending_messages(), 0)
        self.store.add({"type": "empty"})
        self.assertEquals(self.store.count_pending_messages(), 1)
        self.store.add({"type": "data", "data": "yay"})
        self.assertEquals(self.store.count_pending_messages(), 2)

    def test_commit(self):
        """
        The Message Store can be told to save its persistent data to disk on
        demand.
        """
        filename = self.make_path()
        store = MessageStore(Persist(filename=filename), self.temp_dir)
        store.set_accepted_types(["foo", "bar"])

        self.assertFalse(os.path.exists(filename))
        store.commit()
        self.assertTrue(os.path.exists(filename))

        store = MessageStore(Persist(filename=filename), self.temp_dir)
        self.assertEquals(set(store.get_accepted_types()),
                          set(["foo", "bar"]))

    def test_is_pending_pre_and_post_message_delivery(self):
        self.log_helper.ignore_errors(ValueError)

        # We add a couple of messages held and broken, and also a few normal
        # messages before and after, just to increase the chances of breaking
        # due to picking the pending offset incorrectly.
        self.store.set_accepted_types(["empty"])

        # For the same reason we break the first message.
        self.store.add({"type": "empty"})

        filename = os.path.join(self.temp_dir, "0", "0")
        self.assertTrue(os.path.isfile(filename))

        file = open(filename, "w")
        file.write("bpickle will break reading this")
        file.close()

        # And hold the second one.
        self.store.add({"type": "data", "data": "A thing"})

        self.store.add({"type": "empty"})
        self.store.add({"type": "empty"})
        id = self.store.add({"type": "empty"})
        self.store.add({"type": "empty"})
        self.store.add({"type": "empty"})

        # Broken messages will be processed here.
        self.assertTrue(len(self.store.get_pending_messages()), 5)

        self.assertTrue(self.store.is_pending(id))
        self.store.add_pending_offset(2)
        self.assertTrue(self.store.is_pending(id))
        self.store.add_pending_offset(1)
        self.assertFalse(self.store.is_pending(id))

    def test_is_pending_with_held_message(self):

        self.store.set_accepted_types(["empty"])
        id = self.store.add({"type": "data", "data": "A thing"})

        # Add another normal message and increment the pending offset
        # to make the held message stay "behind" in the queue.
        self.store.add({"type": "empty"})
        self.store.add_pending_offset(1)

        self.assertTrue(self.store.is_pending(id))

    def test_is_pending_with_broken_message(self):
        """When a message breaks we consider it to be no longer there."""

        self.log_helper.ignore_errors(ValueError)

        id = self.store.add({"type": "empty"})

        filename = os.path.join(self.temp_dir, "0", "0")
        self.assertTrue(os.path.isfile(filename))

        file = open(filename, "w")
        file.write("bpickle will break reading this")
        file.close()

        self.assertEquals(self.store.get_pending_messages(), [])

        self.assertFalse(self.store.is_pending(id))
