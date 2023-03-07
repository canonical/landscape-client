"""Helpers for reliable persistent message queues."""

RESYNC = object()  # Used as a flag indicating a resync is needed


def got_next_expected(store, next_expected):
    """Our peer has told us what it expects our next message's sequence to be.

    Call this with the message store and sequence number that the peer
    wants next; this will do various things based on what *this* side
    has in its outbound queue store.

    0. The peer expects a sequence number from the server that is too high, the
       difference greater than pending messages in the peer. We flush the older
       messages in queue b/c the server does not want old or ancient messages,
       however we also reset the offset so that the pending messages are
       resent. Then we resynchronize by returning RESYNC. See LP: #1917540

    1. The peer expects a sequence greater than what we last
       sent. This is the common case and generally it should be
       expecting last_sent_sequence+len(messages_sent)+1.

    2. The peer expects a sequence number our side has already sent,
       and we no longer have that message. In this case, just send
       *all* messages we have, including the previous generation,
       starting at the sequence number the peer expects (meaning that
       messages have probably been lost).

    3. The peer expects a sequence number we already sent, and we
       still have that message cached. In this case, we send starting
       from that message.

    If the next expected sequence from the server refers to a message
    older than we have, then L{RESYNC} will be returned.
    """
    ret = None
    old_sequence = store.get_sequence()
    if (next_expected - old_sequence) > store.count_pending_messages():
        store.delete_old_messages()  # Flush queue from previous iteration
        pending_offset = 0  # This means current messages will be resent
        ret = RESYNC
    elif next_expected > old_sequence:
        store.delete_old_messages()
        pending_offset = next_expected - old_sequence
    elif next_expected < (old_sequence - store.get_pending_offset()):
        # "Ancient": The other side wants messages we don't have,
        # so let's just reset our counter to what it expects.
        pending_offset = 0
        ret = RESYNC
    else:
        # No messages transferred, or
        # "Old": We'll try to send these old messages that the
        # other side still wants.
        pending_offset = (
            store.get_pending_offset() + next_expected - old_sequence
        )

    store.set_pending_offset(pending_offset)
    store.set_sequence(next_expected)
    return ret
