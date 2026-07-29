from connectors.base_connector import BaseConnector
from linkers.base_linker import BaseLinker
from translators.base_translator import BaseTranslator
from executors.base_executor import BaseExecutor
from grounders.base_grounder import BaseGrounder

class KGPipeline:

    def __init__(
        self,
        connector: BaseConnector,
        linker: BaseLinker,
        translator: BaseTranslator,
        executor: BaseExecutor,
        grounder: BaseGrounder,
    ):
        self.connector = connector
        self.linker = linker
        self.translator = translator
        self.executor = executor
        self.grounder = grounder

    def run(self, question: str) -> list[dict]:
        """Esegue il ciclo completo dell'agente"""

        # entity linking
        entities = self.linker.link(question)

        # costruzione del contesto
        context_items = []
        for ent in entities:
            qid = getattr(ent, "qid", getattr(ent, "id", ""))
            context_items.append(f"Entità: {ent.label} (wd:{qid})")

        context_items.append("Proprietà data di nascita: wdt:P569")
        schema_context = "\n".join(context_items)

        # translator
        query = self.translator.translate(
            question=question, 
            schema_context=schema_context
        )

        # query execution
        raw_results = self.executor.execute(query)

        # result grounding
        grounded_results = self.grounder.ground(raw_results)

        return grounded_results
