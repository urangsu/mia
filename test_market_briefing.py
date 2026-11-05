import json
import unittest
from dataclasses import replace
from unittest.mock import patch

from test_report_presentation import sample_context
from report_model import _freeze_tables


class MarketBriefingTests(unittest.TestCase):
    def test_official_catalog_filters_deduplicates_and_uses_citation_pages(self):
        from market_briefing import publication_links
        row = dict(indexId='70212345', title='Lithium and nickel supply', publicationDate='2026-10-21',
                   abstract='private-to-render', links=[{'url':'https://example.org/evil'}])
        rows = [row, row, dict(row, indexId='future', publicationDate='2026-11-10'),
                dict(row, indexId='../bad'), dict(row, indexId='irrelevant', title='Ground water'),
                dict(row, indexId='undated', publicationDate='2026')]
        links = publication_links(rows, '2026-10-28')
        self.assertEqual(links, (dict(title='Lithium and nickel supply', date='2026-10-21',
                                     url='https://pubs.usgs.gov/publication/70212345'),))

    def test_unconfigured_summary_does_not_open_network(self):
        from market_briefing import generate_summary
        with patch('market_briefing._read_json') as request:
            self.assertEqual(generate_summary(sample_context(), (), {}), ())
        request.assert_not_called()

    def test_opt_in_sends_only_public_projection_and_ignores_invalid_model_payload(self):
        from market_briefing import generate_summary
        context = sample_context()
        tables = dict(context.tables)
        tables['보고용_금속시세'] += (('PRIVATE-PRICE','2026-10-27',123,'USD/lb','Actual','https://private.test','PRIVATE-CO','코발트',''),)
        context = replace(context, label='일일 시장 보고서', tables=_freeze_tables(tables), workspace_id='SECRET-WORKSPACE', warnings=('SECRET-LOG',))
        env = {'MIA_BRIEFING_ENDPOINT':'https://model.example/v1/chat/completions',
               'MIA_BRIEFING_API_KEY':'test-token', 'MIA_BRIEFING_MODEL':'test-model'}
        with patch('market_briefing._read_json', return_value={'choices':[{'message':{'content':'["코스피는 직전 거래일보다 상승했습니다."]'}}]}) as request:
            self.assertEqual(generate_summary(context, (), env), ('코스피는 직전 거래일보다 상승했습니다.',))
        sent = json.loads(request.call_args.args[0].data)
        content = sent['messages'][1]['content']
        self.assertIn('KOSPI',content)
        for hidden in ('PRIVATE-PRICE','SECRET-WORKSPACE','SECRET-LOG','005930','javascript:'):
            self.assertNotIn(hidden,content)
        with patch('market_briefing._read_json',return_value={'choices':[{'message':{'content':'{}'}}]}):
            self.assertEqual(generate_summary(context, (), env), ())
