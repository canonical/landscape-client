from landscape.client.manager.store import ManagerStore
from landscape.client.tests.helpers import LandscapeTest


class ManagerStoreTest(LandscapeTest):
    def setUp(self):
        super().setUp()
        self.filename = self.makeFile()
        self.store = ManagerStore(self.filename)
        self.store.add_graph(1, "file 1", "user1")
        self.store.set_graph_accumulate(1, 1234, 1.0)

    def test_get_unknown_graph(self):
        graph = self.store.get_graph(1000)
        self.assertIdentical(graph, None)

    def test_get_graph(self):
        graph = self.store.get_graph(1)
        self.assertEqual(graph, (1, "file 1", "user1"))

    def test_get_graphs(self):
        graphs = self.store.get_graphs()
        self.assertEqual(graphs, [(1, "file 1", "user1")])

    def test_get_no_graphs(self):
        self.store.remove_graph(1)
        graphs = self.store.get_graphs()
        self.assertEqual(graphs, [])

    def test_add_graph(self):
        self.store.add_graph(2, "file 2", "user2")
        graph = self.store.get_graph(2)
        self.assertEqual(graph, (2, "file 2", "user2"))

    def test_add_update_graph(self):
        self.store.add_graph(1, "file 2", "user2")
        graph = self.store.get_graph(1)
        self.assertEqual(graph, (1, "file 2", "user2"))

    def test_remove_graph(self):
        self.store.remove_graph(1)
        graphs = self.store.get_graphs()
        self.assertEqual(graphs, [])

    def test_remove_unknown_graph(self):
        self.store.remove_graph(2)
        graphs = self.store.get_graphs()
        self.assertEqual(graphs, [(1, "file 1", "user1")])

    def test_get_accumulate_unknown_graph(self):
        accumulate = self.store.get_graph_accumulate(2)
        self.assertIdentical(accumulate, None)

    def test_set_accumulate_graph(self):
        self.store.set_graph_accumulate(2, 1234, 2.0)
        accumulate = self.store.get_graph_accumulate(2)
        self.assertEqual(accumulate, (2, 1234, 2.0))

    def test_update_accumulate_graph(self):
        self.store.set_graph_accumulate(1, 4567, 2.0)
        accumulate = self.store.get_graph_accumulate(1)
        self.assertEqual(accumulate, (1, 4567, 2.0))
