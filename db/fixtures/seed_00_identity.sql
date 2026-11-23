/* sql_id: seed_identity_branches */
INSERT INTO branches(id, branch_code, branch_name, region_code)
VALUES
    ('11111111-1111-1111-1111-111111111111', 'SYN-GANGNAM', 'SYN 강남센터', 'SEOUL'),
    ('11111111-1111-1111-1111-111111111112', 'SYN-BUSAN', 'SYN 부산센터', 'BUSAN')
ON CONFLICT (branch_code) DO UPDATE SET
    branch_name = EXCLUDED.branch_name,
    region_code = EXCLUDED.region_code;

/* sql_id: seed_identity_employees */
INSERT INTO employees(id, employee_no, name, role_code, branch_id, email, password_hash, is_active)
VALUES
    ('22222222-2222-2222-2222-222222222201', 'SYN-PB-001', '김하준 PB', 'PB', '11111111-1111-1111-1111-111111111111', 'synthetic.pb1@example.invalid', 'pbkdf2_sha256$210000$aGFybmVzcy1zeW50aGV0aWMtbG9naW4tdjE$TnRigzGjhHIQulN42spefAn-WD52ORQD3cVOArd2-sc', TRUE),
    ('22222222-2222-2222-2222-222222222202', 'SYN-WM-001', '이서연 WM', 'WM', '11111111-1111-1111-1111-111111111111', 'synthetic.wm1@example.invalid', 'pbkdf2_sha256$210000$aGFybmVzcy1zeW50aGV0aWMtbG9naW4tdjE$TnRigzGjhHIQulN42spefAn-WD52ORQD3cVOArd2-sc', TRUE),
    ('22222222-2222-2222-2222-222222222203', 'SYN-ADMIN-001', '박도윤 관리자', 'ADMIN', '11111111-1111-1111-1111-111111111111', 'synthetic.admin@example.invalid', 'pbkdf2_sha256$210000$aGFybmVzcy1zeW50aGV0aWMtbG9naW4tdjE$TnRigzGjhHIQulN42spefAn-WD52ORQD3cVOArd2-sc', TRUE),
    ('22222222-2222-2222-2222-222222222204', 'SYN-PB-002', '최민서 PB', 'PB', '11111111-1111-1111-1111-111111111112', 'synthetic.pb2@example.invalid', 'pbkdf2_sha256$210000$aGFybmVzcy1zeW50aGV0aWMtbG9naW4tdjE$TnRigzGjhHIQulN42spefAn-WD52ORQD3cVOArd2-sc', TRUE),
    ('22222222-2222-2222-2222-222222222205', 'SYN-BM-001', '정지우 지점장', 'BRANCH_MANAGER', '11111111-1111-1111-1111-111111111111', 'synthetic.branch.manager@example.invalid', 'pbkdf2_sha256$210000$aGFybmVzcy1zeW50aGV0aWMtbG9naW4tdjE$TnRigzGjhHIQulN42spefAn-WD52ORQD3cVOArd2-sc', TRUE),
    ('22222222-2222-2222-2222-222222222206', 'SYN-AUD-001', '한유진 감사역', 'AUDIT_VIEWER', '11111111-1111-1111-1111-111111111111', 'synthetic.audit@example.invalid', 'pbkdf2_sha256$210000$aGFybmVzcy1zeW50aGV0aWMtbG9naW4tdjE$TnRigzGjhHIQulN42spefAn-WD52ORQD3cVOArd2-sc', TRUE),
    ('22222222-2222-2222-2222-222222222207', 'SYN-CMP-001', '한지민 준법감시인', 'COMPLIANCE_OFFICER', '11111111-1111-1111-1111-111111111111', 'synthetic.compliance@example.invalid', 'pbkdf2_sha256$210000$aGFybmVzcy1zeW50aGV0aWMtbG9naW4tdjE$TnRigzGjhHIQulN42spefAn-WD52ORQD3cVOArd2-sc', TRUE)
ON CONFLICT (employee_no) DO UPDATE SET
    name = EXCLUDED.name,
    role_code = EXCLUDED.role_code,
    branch_id = EXCLUDED.branch_id,
    email = EXCLUDED.email,
    password_hash = EXCLUDED.password_hash,
    is_active = EXCLUDED.is_active;
