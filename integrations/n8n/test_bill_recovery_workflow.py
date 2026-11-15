import unittest

from workflows import BILL, bill_recovery


class BillRecoveryWorkflowTest(unittest.TestCase):
    def test_recovery_preserves_credentials_and_bypasses_mail_download(self):
        credentials = {"sshPrivateKey": {"id": "fixture", "name": "fixture"}}
        workflow = {
            "id": BILL,
            "nodes": [
                {
                    "name": "解密并准备",
                    "credentials": credentials,
                    "parameters": {"command": "old"},
                }
            ],
            "connections": {},
        }
        bill_recovery(workflow)
        bill_recovery(workflow)
        nodes = {node["name"]: node for node in workflow["nodes"]}
        self.assertEqual(len(nodes), 4)
        self.assertEqual(nodes["领取待重试账单"]["credentials"], credentials)
        self.assertIn(
            "bill pending", nodes["领取待重试账单"]["parameters"]["command"]
        )
        self.assertIn(
            "$json.meta_b64 ||", nodes["解密并准备"]["parameters"]["command"]
        )
        target = workflow["connections"]["恢复已保存账单"]["main"][0][0]["node"]
        self.assertEqual(target, "解密并准备")
        self.assertEqual(
            nodes["重试账单定时"]["parameters"]["rule"]["interval"][0][
                "hoursInterval"
            ],
            1,
        )


if __name__ == "__main__":
    unittest.main()
