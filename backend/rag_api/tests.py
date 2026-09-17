from django.test import SimpleTestCase

from rag_api.diversity import cap_per_doc, order_breadth_first
from rag_api.smalltalk import is_smalltalk, smalltalk_reply
from rag_api.text_sanitize import sanitize_text
from rag_api.views import normalize_view_mode


class SmalltalkTests(SimpleTestCase):
    def test_english_greeting_skips_rag(self):
        self.assertTrue(is_smalltalk("Hi"))
        self.assertTrue(is_smalltalk("Hello"))
        self.assertTrue(is_smalltalk("Thanks"))
        self.assertTrue(is_smalltalk("How are you?"))

    def test_arabic_and_urdu_greetings_skip_rag(self):
        self.assertTrue(is_smalltalk("السلام علیکم"))
        self.assertTrue(is_smalltalk("Assalam o Alaikum"))

    def test_legal_questions_are_not_smalltalk(self):
        self.assertFalse(is_smalltalk("What is section 302 of the Pakistan Penal Code?"))
        self.assertFalse(is_smalltalk("پاکستان میں ضمانت کا قانون کیا ہے؟"))
        self.assertFalse(is_smalltalk("ما هو حكم الميراث في الإسلام؟"))

    def test_smalltalk_reply_shape(self):
        payload = smalltalk_reply("Hi", "pakistani")
        self.assertTrue(payload["success"])
        self.assertEqual(payload["selected_agents"], [])
        self.assertIn("legal", payload["answer"].lower())


class ViewModeTests(SimpleTestCase):
    def test_procedure_maps_to_pakistani(self):
        self.assertEqual(normalize_view_mode("procedure"), "pakistani")

    def test_both_is_allowed(self):
        self.assertEqual(normalize_view_mode("both"), "both")

    def test_invalid_rejected(self):
        self.assertIsNone(normalize_view_mode("court"))


class DiversityTests(SimpleTestCase):
    def test_cap_per_doc(self):
        chunks = [
            {"doc_id": "A", "chunk_id": "a1"},
            {"doc_id": "A", "chunk_id": "a2"},
            {"doc_id": "A", "chunk_id": "a3"},
            {"doc_id": "B", "chunk_id": "b1"},
        ]
        capped = cap_per_doc(chunks, 2)
        self.assertEqual([c["chunk_id"] for c in capped], ["a1", "a2", "b1"])

    def test_breadth_first_keeps_overflow(self):
        chunks = [
            {"doc_id": "A", "chunk_id": "a1"},
            {"doc_id": "A", "chunk_id": "a2"},
            {"doc_id": "B", "chunk_id": "b1"},
            {"doc_id": "A", "chunk_id": "a3"},
        ]
        ordered = order_breadth_first(chunks, 2)
        self.assertEqual([c["chunk_id"] for c in ordered], ["a1", "a2", "b1", "a3"])


class MasterDecisionTests(SimpleTestCase):
    def test_query_class_defaults_and_agents_unique(self):
        from rag_api.rag_service import MasterDecision

        decision = MasterDecision(
            in_scope=True,
            standalone_question="What is section 302 PPC?",
            topic="ppc homicide",
            memory_hit=False,
            memory_reason="none",
            selected_agents=["pakistani_agent", "pakistani_agent"],
        )
        self.assertEqual(decision.query_class, "DOMAIN_QUERY")
        self.assertEqual(decision.selected_agents, ["pakistani_agent"])

    def test_sub_queries_main_key_is_accepted_then_assigned(self):
        from rag_api.rag_service import MasterDecision, _assign_sub_queries

        decision = MasterDecision(
            in_scope=True,
            standalone_question="who can dissolve national assembly of Pakistan",
            topic="dissolution",
            memory_hit=False,
            memory_reason="none",
            selected_agents=["pakistani_agent"],
            sub_queries={"main": "who can dissolve national assembly of Pakistan"},
        )
        assigned = _assign_sub_queries(
            decision.sub_queries,
            ["pakistani_agent"],
            decision.standalone_question,
        )
        self.assertEqual(
            assigned["pakistani_agent"],
            "who can dissolve national assembly of Pakistan",
        )

    def test_recover_failed_generation_arguments(self):
        from rag_api.rag_service import RAGService

        message = (
            "Error code: 400 - {'error': {'message': \"Tool call validation failed\", "
            "'failed_generation': '{\"name\": \"MasterDecision\", \"arguments\": "
            '{\"in_scope\":true,\"query_class\":\"DOMAIN_QUERY\",\"standalone_question\":'
            '\"who can dissolve national assembly of Pakistan\",\"topic\":\"dissolution\",'
            '\"memory_hit\":false,\"memory_reason\":\"none\",\"selected_agents\":'
            '[\"pakistani_agent\"],\"sub_queries\":{\"main\":\"who can dissolve '
            'national assembly of Pakistan\"},\"routing_reason\":\"ok\"}}\'}}'
        )
        recovered = RAGService._parse_failed_generation(Exception(message))
        self.assertIsNotNone(recovered)
        self.assertTrue(recovered["in_scope"])
        self.assertIn("main", recovered["sub_queries"])

    def test_evidence_sufficiency(self):
        from rag_api.rag_service import RAGService

        empty = RAGService._evidence_is_sufficient([])
        self.assertFalse(empty)
        weak = RAGService._evidence_is_sufficient(
            [
                {
                    "source_id": "PK-1",
                    "agent": "pakistani_agent",
                    "content": "short",
                    "metadata": {},
                    "retrieval_score": 0.1,
                    "rerank_score": 0.0,
                    "doc_id": "d1",
                }
            ]
        )
        self.assertFalse(weak)
        # Negative rerank logits are common for BGE; content length matters.
        negative_score = RAGService._evidence_is_sufficient(
            [
                {
                    "source_id": "IS-1",
                    "agent": "islamic_agent",
                    "content": "The Hudood ordinances address zina and related offences in Islamic criminal law.",
                    "metadata": {},
                    "retrieval_score": 0.4,
                    "rerank_score": -1.25,
                    "doc_id": "d2",
                }
            ]
        )
        self.assertTrue(negative_score)
        strong = RAGService._evidence_is_sufficient(
            [
                {
                    "source_id": "PK-1",
                    "agent": "pakistani_agent",
                    "content": "Section 302 of the Pakistan Penal Code deals with murder.",
                    "metadata": {},
                    "retrieval_score": 0.8,
                    "rerank_score": 0.7,
                    "doc_id": "d1",
                }
            ]
        )
        self.assertTrue(strong)

    def test_domain_hint_detects_hudood(self):
        from rag_api.rag_service import _looks_domain_related, _looks_clearly_out_of_domain

        self.assertTrue(_looks_domain_related("What does Hudood say about zina?"))
        self.assertFalse(_looks_clearly_out_of_domain("What does Hudood say about zina?"))
        self.assertTrue(_looks_clearly_out_of_domain("What is the capital of France?"))


class SanitizeTests(SimpleTestCase):
    def test_nfc_and_replacement_char(self):
        self.assertEqual(sanitize_text("Bohras\ufffds house"), "Bohras's house")
        self.assertEqual(sanitize_text("  hello\n\n\nworld  "), "hello\n\nworld")


class FilterTests(SimpleTestCase):
    def test_pakistani_filter_does_not_include_language(self):
        try:
            from rag_api.retriever import HybridRetriever
        except ImportError:
            self.skipTest("qdrant-client is not installed")
        built = HybridRetriever.build_filter(legal_system="Pakistani", province="Punjab")
        text = str(built.model_dump() if hasattr(built, "model_dump") else built)
        self.assertIn("legal_system", text)
        self.assertNotIn("'language'", text)
        self.assertNotIn('"language"', text)

    def test_islamic_filter_is_legal_system_only(self):
        try:
            from rag_api.retriever import HybridRetriever
        except ImportError:
            self.skipTest("qdrant-client is not installed")
        built = HybridRetriever.build_filter(legal_system="Islamic")
        self.assertIsNotNone(built)

    def test_no_filter_when_nothing_set(self):
        try:
            from rag_api.retriever import HybridRetriever
        except ImportError:
            self.skipTest("qdrant-client is not installed")
        self.assertIsNone(HybridRetriever.build_filter())
