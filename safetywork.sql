/*
 Navicat Premium Dump SQL

 Source Server         : Linhai_local
 Source Server Type    : MySQL
 Source Server Version : 50743 (5.7.43-log)
 Source Host           : localhost:3306
 Source Schema         : safetywork

 Target Server Type    : MySQL
 Target Server Version : 50743 (5.7.43-log)
 File Encoding         : 65001

 Date: 08/05/2026 16:24:31
*/

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ----------------------------
-- Table structure for security_event_log
-- ----------------------------
DROP TABLE IF EXISTS `security_event_log`;
CREATE TABLE `security_event_log`  (
  `event_id` bigint(20) UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '安全事件 ID',
  `user_id` bigint(20) UNSIGNED NULL DEFAULT NULL COMMENT '关联用户 ID；登录失败或用户名不存在时允许为空',
  `username` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '用户名快照，便于追踪登录失败或非法请求',
  `event_type` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '事件类型，如 REGISTER、LOGIN_SUCCESS、LOGIN_FAIL、CHANGE_PASSWORD、TICKET_EXPIRED、REPLAY_BLOCKED',
  `result` tinyint(3) UNSIGNED NOT NULL COMMENT '事件结果：1 成功，0 失败',
  `client_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '客户端运行期实例 ID，仅记录报文中携带的 clientId',
  `remote_addr` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT 'WebSocket 连接远端地址，仅用于审计',
  `reason` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '失败原因或安全事件原因',
  `created_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '事件发生时间',
  PRIMARY KEY (`event_id`) USING BTREE,
  INDEX `idx_security_event_user_time`(`user_id`, `created_at`) USING BTREE,
  INDEX `idx_security_event_type_time`(`event_type`, `created_at`) USING BTREE,
  CONSTRAINT `fk_security_event_user` FOREIGN KEY (`user_id`) REFERENCES `user_account` (`user_id`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE = InnoDB AUTO_INCREMENT = 228 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = 'AS 安全事件日志表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of security_event_log
-- ----------------------------
INSERT INTO `security_event_log` VALUES (1, 1, 'tgs_smoke_6b21af42bc', 'REGISTER', 1, 'cli-tgs-smoke-6b21af42bc', '127.0.0.1:55988', NULL, '2026-05-07 22:48:31.454');
INSERT INTO `security_event_log` VALUES (2, 2, 'tgs_smoke_9cb1590d51', 'REGISTER', 1, 'cli-tgs-smoke-9cb1590d51', '127.0.0.1:58913', NULL, '2026-05-07 22:51:44.413');
INSERT INTO `security_event_log` VALUES (3, 3, 'tgs_smoke_03a517c139', 'REGISTER', 1, 'cli-tgs-smoke-03a517c139', '127.0.0.1:57640', NULL, '2026-05-07 22:55:28.071');
INSERT INTO `security_event_log` VALUES (4, 4, 'tgs_smoke_60a807bac6', 'REGISTER', 1, 'cli-tgs-smoke-60a807bac6', '127.0.0.1:56122', NULL, '2026-05-07 23:00:48.995');
INSERT INTO `security_event_log` VALUES (5, 4, 'tgs_smoke_60a807bac6', 'LOGIN_SUCCESS', 1, 'cli-tgs-smoke-60a807bac6', '127.0.0.1:56122', NULL, '2026-05-07 23:00:49.108');
INSERT INTO `security_event_log` VALUES (6, NULL, NULL, 'TGS_ISSUE_FAIL', 0, 'cli-tgs-smoke-60a807bac6', '127.0.0.1:56125', 'pycryptodome is required for DES-CBC support; install tgs/requirements.txt', '2026-05-07 23:00:49.146');
INSERT INTO `security_event_log` VALUES (7, 5, 'tgs_smoke_ad34582274', 'REGISTER', 1, 'cli-tgs-smoke-ad34582274', '127.0.0.1:49275', NULL, '2026-05-07 23:05:35.357');
INSERT INTO `security_event_log` VALUES (8, 5, 'tgs_smoke_ad34582274', 'LOGIN_SUCCESS', 1, 'cli-tgs-smoke-ad34582274', '127.0.0.1:49275', NULL, '2026-05-07 23:05:35.484');
INSERT INTO `security_event_log` VALUES (9, 5, 'tgs_smoke_ad34582274', 'TGS_ISSUE_SUCCESS', 1, 'cli-tgs-smoke-ad34582274', '127.0.0.1:49278', NULL, '2026-05-07 23:05:35.544');
INSERT INTO `security_event_log` VALUES (10, NULL, NULL, 'GS_AUTH_FAIL', 0, 'cli_0550ed7afc6849d98bef98b5a2f8082d', '127.0.0.1:56959', 'INVALID_BASE64', '2026-05-07 23:24:36.882');
INSERT INTO `security_event_log` VALUES (11, 6, 'testuser', 'REGISTER', 1, 'cli_f89392bd0eb541809fa42b5785316d25', '127.0.0.1:56462', NULL, '2026-05-07 23:38:54.061');
INSERT INTO `security_event_log` VALUES (12, 6, 'testuser', 'LOGIN_SUCCESS', 1, 'cli_f89392bd0eb541809fa42b5785316d25', '127.0.0.1:60281', NULL, '2026-05-07 23:39:41.255');
INSERT INTO `security_event_log` VALUES (13, 6, 'testuser', 'TGS_ISSUE_SUCCESS', 1, 'cli_f89392bd0eb541809fa42b5785316d25', '127.0.0.1:60283', NULL, '2026-05-07 23:39:41.610');
INSERT INTO `security_event_log` VALUES (14, 6, 'testuser', 'LOGIN_SUCCESS', 1, 'cli_1efef599095e4e1f9d70703d9d56ff43', '127.0.0.1:54941', NULL, '2026-05-07 23:46:36.517');
INSERT INTO `security_event_log` VALUES (15, 6, 'testuser', 'TGS_ISSUE_SUCCESS', 1, 'cli_1efef599095e4e1f9d70703d9d56ff43', '127.0.0.1:54943', NULL, '2026-05-07 23:46:36.926');
INSERT INTO `security_event_log` VALUES (16, 6, 'testuser', 'GS_AUTH_SUCCESS', 1, 'cli_1efef599095e4e1f9d70703d9d56ff43', '127.0.0.1:60402', NULL, '2026-05-07 23:46:45.059');
INSERT INTO `security_event_log` VALUES (17, 6, 'testuser', 'LOGIN_SUCCESS', 1, 'cli_8470912cb48c4963bc6cbdff9ee9ca9d', '127.0.0.1:58778', NULL, '2026-05-07 23:50:03.642');
INSERT INTO `security_event_log` VALUES (18, 6, 'testuser', 'TGS_ISSUE_SUCCESS', 1, 'cli_8470912cb48c4963bc6cbdff9ee9ca9d', '127.0.0.1:58780', NULL, '2026-05-07 23:50:03.988');
INSERT INTO `security_event_log` VALUES (19, 6, 'testuser', 'GS_AUTH_SUCCESS', 1, 'cli_8470912cb48c4963bc6cbdff9ee9ca9d', '127.0.0.1:58783', NULL, '2026-05-07 23:50:06.400');
INSERT INTO `security_event_log` VALUES (20, 6, 'testuser', 'LOGIN_SUCCESS', 1, 'cli_4d6bd29af1e3457f9a965c167457f3be', '127.0.0.1:58404', NULL, '2026-05-07 23:55:09.827');
INSERT INTO `security_event_log` VALUES (21, 6, 'testuser', 'TGS_ISSUE_SUCCESS', 1, 'cli_4d6bd29af1e3457f9a965c167457f3be', '127.0.0.1:58406', NULL, '2026-05-07 23:55:10.198');
INSERT INTO `security_event_log` VALUES (22, 6, 'testuser', 'GS_AUTH_SUCCESS', 1, 'cli_4d6bd29af1e3457f9a965c167457f3be', '127.0.0.1:58410', NULL, '2026-05-07 23:55:11.654');
INSERT INTO `security_event_log` VALUES (23, NULL, 'creo', 'REGISTER', 0, 'cli_84dcf7fa505e48b78746b829fbb725d0', '127.0.0.1:59405', 'WEAK_PASSWORD', '2026-05-08 02:23:16.760');
INSERT INTO `security_event_log` VALUES (24, NULL, 'creo', 'REGISTER', 0, 'cli_84dcf7fa505e48b78746b829fbb725d0', '127.0.0.1:63286', 'WEAK_PASSWORD', '2026-05-08 02:23:33.740');
INSERT INTO `security_event_log` VALUES (25, 7, 'testuser1', 'REGISTER', 1, 'cli_84dcf7fa505e48b78746b829fbb725d0', '127.0.0.1:52865', NULL, '2026-05-08 02:24:02.277');
INSERT INTO `security_event_log` VALUES (26, 7, 'testuser1', 'LOGIN_SUCCESS', 1, 'cli_84dcf7fa505e48b78746b829fbb725d0', '127.0.0.1:52875', NULL, '2026-05-08 02:24:05.882');
INSERT INTO `security_event_log` VALUES (27, 7, 'testuser1', 'TGS_ISSUE_SUCCESS', 1, 'cli_84dcf7fa505e48b78746b829fbb725d0', '127.0.0.1:52879', NULL, '2026-05-08 02:24:06.409');
INSERT INTO `security_event_log` VALUES (28, 7, 'testuser1', 'GS_AUTH_SUCCESS', 1, 'cli_84dcf7fa505e48b78746b829fbb725d0', '127.0.0.1:52881', NULL, '2026-05-08 02:24:06.485');
INSERT INTO `security_event_log` VALUES (29, NULL, 'linhai1', 'REGISTER', 0, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:57430', 'WEAK_PASSWORD', '2026-05-08 02:36:32.062');
INSERT INTO `security_event_log` VALUES (30, 8, 'linhai1', 'REGISTER', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:57436', NULL, '2026-05-08 02:36:48.311');
INSERT INTO `security_event_log` VALUES (31, 8, 'linhai1', 'LOGIN_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:57438', NULL, '2026-05-08 02:36:49.968');
INSERT INTO `security_event_log` VALUES (32, 8, 'linhai1', 'TGS_ISSUE_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:57443', NULL, '2026-05-08 02:36:50.369');
INSERT INTO `security_event_log` VALUES (33, 8, 'linhai1', 'GS_AUTH_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:57445', NULL, '2026-05-08 02:36:50.441');
INSERT INTO `security_event_log` VALUES (34, NULL, 'linhai2', 'REGISTER', 0, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:60049', 'WEAK_PASSWORD', '2026-05-08 02:37:20.885');
INSERT INTO `security_event_log` VALUES (35, 9, 'linhai2', 'REGISTER', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:56013', NULL, '2026-05-08 02:37:38.128');
INSERT INTO `security_event_log` VALUES (36, 9, 'linhai2', 'LOGIN_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:56015', NULL, '2026-05-08 02:37:39.210');
INSERT INTO `security_event_log` VALUES (37, 9, 'linhai2', 'TGS_ISSUE_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:56017', NULL, '2026-05-08 02:37:39.677');
INSERT INTO `security_event_log` VALUES (38, 9, 'linhai2', 'GS_AUTH_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:56019', NULL, '2026-05-08 02:37:39.765');
INSERT INTO `security_event_log` VALUES (39, 9, 'linhai2', 'LOGIN_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:52016', NULL, '2026-05-08 02:39:08.077');
INSERT INTO `security_event_log` VALUES (40, 9, 'linhai2', 'TGS_ISSUE_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:52018', NULL, '2026-05-08 02:39:08.531');
INSERT INTO `security_event_log` VALUES (41, 8, 'linhai1', 'LOGIN_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:65530', NULL, '2026-05-08 02:39:48.464');
INSERT INTO `security_event_log` VALUES (42, 8, 'linhai1', 'TGS_ISSUE_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:65532', NULL, '2026-05-08 02:39:48.848');
INSERT INTO `security_event_log` VALUES (43, 8, 'linhai1', 'GS_AUTH_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:65534', NULL, '2026-05-08 02:39:48.942');
INSERT INTO `security_event_log` VALUES (44, 8, 'linhai1', 'LOGIN_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:49155', NULL, '2026-05-08 02:39:54.447');
INSERT INTO `security_event_log` VALUES (45, 8, 'linhai1', 'TGS_ISSUE_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:49157', NULL, '2026-05-08 02:39:54.935');
INSERT INTO `security_event_log` VALUES (46, 8, 'linhai1', 'LOGIN_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:52867', NULL, '2026-05-08 02:41:22.946');
INSERT INTO `security_event_log` VALUES (47, 8, 'linhai1', 'TGS_ISSUE_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:52869', NULL, '2026-05-08 02:41:23.302');
INSERT INTO `security_event_log` VALUES (48, 8, 'linhai1', 'GS_AUTH_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:52871', NULL, '2026-05-08 02:41:23.373');
INSERT INTO `security_event_log` VALUES (49, 9, 'linhai2', 'LOGIN_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:64919', NULL, '2026-05-08 02:41:52.232');
INSERT INTO `security_event_log` VALUES (50, 9, 'linhai2', 'TGS_ISSUE_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:64924', NULL, '2026-05-08 02:41:52.694');
INSERT INTO `security_event_log` VALUES (51, 9, 'linhai2', 'GS_AUTH_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:64926', NULL, '2026-05-08 02:41:52.763');
INSERT INTO `security_event_log` VALUES (52, 8, 'linhai1', 'LOGIN_SUCCESS', 1, 'cli_fa7f899766514d80a6fea24912f73ba2', '127.0.0.1:56271', NULL, '2026-05-08 03:27:56.356');
INSERT INTO `security_event_log` VALUES (53, 8, 'linhai1', 'TGS_ISSUE_SUCCESS', 1, 'cli_fa7f899766514d80a6fea24912f73ba2', '127.0.0.1:56279', NULL, '2026-05-08 03:27:56.815');
INSERT INTO `security_event_log` VALUES (54, 8, 'linhai1', 'GS_AUTH_SUCCESS', 1, 'cli_fa7f899766514d80a6fea24912f73ba2', '127.0.0.1:56281', NULL, '2026-05-08 03:27:56.895');
INSERT INTO `security_event_log` VALUES (55, 9, 'linhai2', 'LOGIN_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:52477', NULL, '2026-05-08 03:30:38.786');
INSERT INTO `security_event_log` VALUES (56, 9, 'linhai2', 'TGS_ISSUE_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:52482', NULL, '2026-05-08 03:30:39.286');
INSERT INTO `security_event_log` VALUES (57, 9, 'linhai2', 'GS_AUTH_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:52485', NULL, '2026-05-08 03:30:39.374');
INSERT INTO `security_event_log` VALUES (58, 9, 'linhai2', 'LOGIN_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:52491', NULL, '2026-05-08 03:30:43.676');
INSERT INTO `security_event_log` VALUES (59, 9, 'linhai2', 'TGS_ISSUE_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:52493', NULL, '2026-05-08 03:30:44.208');
INSERT INTO `security_event_log` VALUES (60, 8, 'linhai1', 'LOGIN_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:58984', NULL, '2026-05-08 03:32:26.610');
INSERT INTO `security_event_log` VALUES (61, 8, 'linhai1', 'TGS_ISSUE_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:58988', NULL, '2026-05-08 03:32:27.205');
INSERT INTO `security_event_log` VALUES (62, 8, 'linhai1', 'GS_AUTH_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:58990', NULL, '2026-05-08 03:32:27.282');
INSERT INTO `security_event_log` VALUES (63, 9, 'linhai2', 'LOGIN_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:59036', NULL, '2026-05-08 03:33:06.578');
INSERT INTO `security_event_log` VALUES (64, 9, 'linhai2', 'TGS_ISSUE_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:59040', NULL, '2026-05-08 03:33:07.113');
INSERT INTO `security_event_log` VALUES (65, 9, 'linhai2', 'GS_AUTH_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:59042', NULL, '2026-05-08 03:33:07.182');
INSERT INTO `security_event_log` VALUES (66, 9, 'linhai2', 'LOGIN_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:59053', NULL, '2026-05-08 03:33:10.278');
INSERT INTO `security_event_log` VALUES (67, 9, 'linhai2', 'TGS_ISSUE_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:59055', NULL, '2026-05-08 03:33:10.802');
INSERT INTO `security_event_log` VALUES (68, 9, 'linhai2', 'LOGIN_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:57192', NULL, '2026-05-08 03:39:03.077');
INSERT INTO `security_event_log` VALUES (69, 9, 'linhai2', 'TGS_ISSUE_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:57197', NULL, '2026-05-08 03:39:03.636');
INSERT INTO `security_event_log` VALUES (70, 9, 'linhai2', 'GS_AUTH_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:57200', NULL, '2026-05-08 03:39:03.711');
INSERT INTO `security_event_log` VALUES (71, 8, 'linhai1', 'LOGIN_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:57211', NULL, '2026-05-08 03:39:18.821');
INSERT INTO `security_event_log` VALUES (72, 8, 'linhai1', 'TGS_ISSUE_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:57213', NULL, '2026-05-08 03:39:19.340');
INSERT INTO `security_event_log` VALUES (73, 8, 'linhai1', 'GS_AUTH_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:57215', NULL, '2026-05-08 03:39:19.412');
INSERT INTO `security_event_log` VALUES (74, 8, 'linhai1', 'LOGIN_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:57177', NULL, '2026-05-08 04:11:53.259');
INSERT INTO `security_event_log` VALUES (75, 8, 'linhai1', 'TGS_ISSUE_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:57179', NULL, '2026-05-08 04:11:53.754');
INSERT INTO `security_event_log` VALUES (76, 8, 'linhai1', 'GS_AUTH_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:57181', NULL, '2026-05-08 04:11:53.824');
INSERT INTO `security_event_log` VALUES (77, 8, 'linhai1', 'LOGIN_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:56971', NULL, '2026-05-08 04:22:22.316');
INSERT INTO `security_event_log` VALUES (78, 8, 'linhai1', 'TGS_ISSUE_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:56975', NULL, '2026-05-08 04:22:22.725');
INSERT INTO `security_event_log` VALUES (79, 8, 'linhai1', 'GS_AUTH_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:56977', NULL, '2026-05-08 04:22:22.823');
INSERT INTO `security_event_log` VALUES (80, 8, 'linhai1', 'LOGIN_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:63490', NULL, '2026-05-08 04:24:34.043');
INSERT INTO `security_event_log` VALUES (81, 8, 'linhai1', 'TGS_ISSUE_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:63492', NULL, '2026-05-08 04:24:34.543');
INSERT INTO `security_event_log` VALUES (82, 8, 'linhai1', 'GS_AUTH_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:63494', NULL, '2026-05-08 04:24:34.615');
INSERT INTO `security_event_log` VALUES (83, 8, 'linhai1', 'LOGIN_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:54799', NULL, '2026-05-08 04:27:48.520');
INSERT INTO `security_event_log` VALUES (84, 8, 'linhai1', 'TGS_ISSUE_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:54801', NULL, '2026-05-08 04:27:49.009');
INSERT INTO `security_event_log` VALUES (85, 8, 'linhai1', 'GS_AUTH_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:54803', NULL, '2026-05-08 04:27:49.102');
INSERT INTO `security_event_log` VALUES (86, 8, 'linhai1', 'LOGIN_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:55708', NULL, '2026-05-08 04:34:26.699');
INSERT INTO `security_event_log` VALUES (87, 8, 'linhai1', 'TGS_ISSUE_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:55714', NULL, '2026-05-08 04:34:27.140');
INSERT INTO `security_event_log` VALUES (88, 8, 'linhai1', 'GS_AUTH_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:55716', NULL, '2026-05-08 04:34:27.211');
INSERT INTO `security_event_log` VALUES (89, 8, 'linhai1', 'LOGIN_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:54688', NULL, '2026-05-08 04:42:13.607');
INSERT INTO `security_event_log` VALUES (90, 8, 'linhai1', 'TGS_ISSUE_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:54690', NULL, '2026-05-08 04:42:14.074');
INSERT INTO `security_event_log` VALUES (91, 8, 'linhai1', 'GS_AUTH_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:54692', NULL, '2026-05-08 04:42:14.168');
INSERT INTO `security_event_log` VALUES (92, 8, 'linhai1', 'LOGIN_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:60827', NULL, '2026-05-08 04:56:20.506');
INSERT INTO `security_event_log` VALUES (93, 8, 'linhai1', 'TGS_ISSUE_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:60829', NULL, '2026-05-08 04:56:20.977');
INSERT INTO `security_event_log` VALUES (94, 8, 'linhai1', 'GS_AUTH_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:60831', NULL, '2026-05-08 04:56:21.050');
INSERT INTO `security_event_log` VALUES (95, 8, 'linhai1', 'LOGIN_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:57379', NULL, '2026-05-08 04:59:49.049');
INSERT INTO `security_event_log` VALUES (96, 8, 'linhai1', 'TGS_ISSUE_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:57381', NULL, '2026-05-08 04:59:49.643');
INSERT INTO `security_event_log` VALUES (97, 8, 'linhai1', 'GS_AUTH_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:57383', NULL, '2026-05-08 04:59:49.749');
INSERT INTO `security_event_log` VALUES (98, 8, 'linhai1', 'LOGIN_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:63382', NULL, '2026-05-08 05:02:39.673');
INSERT INTO `security_event_log` VALUES (99, 8, 'linhai1', 'TGS_ISSUE_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:63384', NULL, '2026-05-08 05:02:40.148');
INSERT INTO `security_event_log` VALUES (100, 8, 'linhai1', 'GS_AUTH_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:63386', NULL, '2026-05-08 05:02:40.253');
INSERT INTO `security_event_log` VALUES (101, 8, 'linhai1', 'LOGIN_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:58127', NULL, '2026-05-08 05:05:02.223');
INSERT INTO `security_event_log` VALUES (102, 8, 'linhai1', 'TGS_ISSUE_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:58134', NULL, '2026-05-08 05:05:02.662');
INSERT INTO `security_event_log` VALUES (103, 8, 'linhai1', 'GS_AUTH_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:58136', NULL, '2026-05-08 05:05:02.738');
INSERT INTO `security_event_log` VALUES (104, 8, 'linhai1', 'LOGIN_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:60673', NULL, '2026-05-08 05:05:34.627');
INSERT INTO `security_event_log` VALUES (105, 8, 'linhai1', 'TGS_ISSUE_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:60675', NULL, '2026-05-08 05:05:35.028');
INSERT INTO `security_event_log` VALUES (106, 8, 'linhai1', 'GS_AUTH_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:60677', NULL, '2026-05-08 05:05:35.117');
INSERT INTO `security_event_log` VALUES (107, 8, 'linhai1', 'LOGIN_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:57582', NULL, '2026-05-08 05:09:05.244');
INSERT INTO `security_event_log` VALUES (108, 8, 'linhai1', 'TGS_ISSUE_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:57584', NULL, '2026-05-08 05:09:05.677');
INSERT INTO `security_event_log` VALUES (109, 8, 'linhai1', 'GS_AUTH_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:57586', NULL, '2026-05-08 05:09:05.773');
INSERT INTO `security_event_log` VALUES (110, 8, 'linhai1', 'LOGIN_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:64713', NULL, '2026-05-08 05:17:22.301');
INSERT INTO `security_event_log` VALUES (111, 8, 'linhai1', 'TGS_ISSUE_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:64715', NULL, '2026-05-08 05:17:22.681');
INSERT INTO `security_event_log` VALUES (112, 8, 'linhai1', 'GS_AUTH_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:64717', NULL, '2026-05-08 05:17:22.750');
INSERT INTO `security_event_log` VALUES (113, 8, 'linhai1', 'LOGIN_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:64735', NULL, '2026-05-08 05:17:35.587');
INSERT INTO `security_event_log` VALUES (114, 8, 'linhai1', 'TGS_ISSUE_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:64737', NULL, '2026-05-08 05:17:35.932');
INSERT INTO `security_event_log` VALUES (115, 8, 'linhai1', 'GS_AUTH_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:64739', NULL, '2026-05-08 05:17:36.014');
INSERT INTO `security_event_log` VALUES (116, 8, 'linhai1', 'LOGIN_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:62703', NULL, '2026-05-08 05:21:19.552');
INSERT INTO `security_event_log` VALUES (117, 8, 'linhai1', 'TGS_ISSUE_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:62705', NULL, '2026-05-08 05:21:19.909');
INSERT INTO `security_event_log` VALUES (118, 8, 'linhai1', 'GS_AUTH_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:62707', NULL, '2026-05-08 05:21:19.977');
INSERT INTO `security_event_log` VALUES (119, 8, 'linhai1', 'LOGIN_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:62740', NULL, '2026-05-08 05:21:48.243');
INSERT INTO `security_event_log` VALUES (120, 8, 'linhai1', 'TGS_ISSUE_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:62742', NULL, '2026-05-08 05:21:48.582');
INSERT INTO `security_event_log` VALUES (121, 8, 'linhai1', 'GS_AUTH_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:62744', NULL, '2026-05-08 05:21:48.661');
INSERT INTO `security_event_log` VALUES (122, 8, 'linhai1', 'LOGIN_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:64375', NULL, '2026-05-08 05:24:42.264');
INSERT INTO `security_event_log` VALUES (123, 8, 'linhai1', 'TGS_ISSUE_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:64377', NULL, '2026-05-08 05:24:42.742');
INSERT INTO `security_event_log` VALUES (124, 8, 'linhai1', 'GS_AUTH_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:64379', NULL, '2026-05-08 05:24:42.839');
INSERT INTO `security_event_log` VALUES (125, 8, 'linhai1', 'LOGIN_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:49811', NULL, '2026-05-08 05:27:23.662');
INSERT INTO `security_event_log` VALUES (126, 8, 'linhai1', 'TGS_ISSUE_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:49813', NULL, '2026-05-08 05:27:24.038');
INSERT INTO `security_event_log` VALUES (127, 8, 'linhai1', 'GS_AUTH_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:49815', NULL, '2026-05-08 05:27:24.115');
INSERT INTO `security_event_log` VALUES (128, 8, 'linhai1', 'LOGIN_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:52519', NULL, '2026-05-08 05:28:52.305');
INSERT INTO `security_event_log` VALUES (129, 8, 'linhai1', 'TGS_ISSUE_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:52521', NULL, '2026-05-08 05:28:52.708');
INSERT INTO `security_event_log` VALUES (130, 8, 'linhai1', 'GS_AUTH_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:52524', NULL, '2026-05-08 05:28:52.798');
INSERT INTO `security_event_log` VALUES (131, 8, 'linhai1', 'LOGIN_FAIL', 0, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:51867', 'BAD_CREDENTIALS', '2026-05-08 05:30:26.761');
INSERT INTO `security_event_log` VALUES (132, 8, 'linhai1', 'LOGIN_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:60113', NULL, '2026-05-08 05:30:35.367');
INSERT INTO `security_event_log` VALUES (133, 8, 'linhai1', 'TGS_ISSUE_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:60117', NULL, '2026-05-08 05:30:35.765');
INSERT INTO `security_event_log` VALUES (134, 8, 'linhai1', 'GS_AUTH_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:60119', NULL, '2026-05-08 05:30:35.832');
INSERT INTO `security_event_log` VALUES (135, 9, 'linhai2', 'LOGIN_FAIL', 0, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:60129', 'BAD_CREDENTIALS', '2026-05-08 05:30:53.998');
INSERT INTO `security_event_log` VALUES (136, 9, 'linhai2', 'LOGIN_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:60143', NULL, '2026-05-08 05:31:01.676');
INSERT INTO `security_event_log` VALUES (137, 9, 'linhai2', 'TGS_ISSUE_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:60145', NULL, '2026-05-08 05:31:02.056');
INSERT INTO `security_event_log` VALUES (138, 9, 'linhai2', 'GS_AUTH_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:60147', NULL, '2026-05-08 05:31:02.120');
INSERT INTO `security_event_log` VALUES (139, 8, 'linhai1', 'LOGIN_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:58895', NULL, '2026-05-08 05:32:44.025');
INSERT INTO `security_event_log` VALUES (140, 8, 'linhai1', 'TGS_ISSUE_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:58897', NULL, '2026-05-08 05:32:44.382');
INSERT INTO `security_event_log` VALUES (141, 8, 'linhai1', 'GS_AUTH_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:58899', NULL, '2026-05-08 05:32:44.448');
INSERT INTO `security_event_log` VALUES (142, 8, 'linhai1', 'LOGIN_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:52760', NULL, '2026-05-08 05:36:47.417');
INSERT INTO `security_event_log` VALUES (143, 8, 'linhai1', 'TGS_ISSUE_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:52762', NULL, '2026-05-08 05:36:47.751');
INSERT INTO `security_event_log` VALUES (144, 8, 'linhai1', 'GS_AUTH_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:52764', NULL, '2026-05-08 05:36:47.837');
INSERT INTO `security_event_log` VALUES (145, 8, 'linhai1', 'LOGIN_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:57612', NULL, '2026-05-08 05:37:55.804');
INSERT INTO `security_event_log` VALUES (146, 8, 'linhai1', 'TGS_ISSUE_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:57614', NULL, '2026-05-08 05:37:56.214');
INSERT INTO `security_event_log` VALUES (147, 8, 'linhai1', 'GS_AUTH_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:57616', NULL, '2026-05-08 05:37:56.293');
INSERT INTO `security_event_log` VALUES (148, 8, 'linhai1', 'LOGIN_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:57876', NULL, '2026-05-08 05:40:26.193');
INSERT INTO `security_event_log` VALUES (149, 8, 'linhai1', 'TGS_ISSUE_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:59176', NULL, '2026-05-08 05:40:26.534');
INSERT INTO `security_event_log` VALUES (150, 8, 'linhai1', 'GS_AUTH_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:59178', NULL, '2026-05-08 05:40:26.615');
INSERT INTO `security_event_log` VALUES (151, 8, 'linhai1', 'LOGIN_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:63181', NULL, '2026-05-08 05:45:44.949');
INSERT INTO `security_event_log` VALUES (152, 8, 'linhai1', 'TGS_ISSUE_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:63183', NULL, '2026-05-08 05:45:45.399');
INSERT INTO `security_event_log` VALUES (153, 8, 'linhai1', 'GS_AUTH_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:63185', NULL, '2026-05-08 05:45:45.478');
INSERT INTO `security_event_log` VALUES (154, 8, 'linhai1', 'LOGIN_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:55220', NULL, '2026-05-08 05:47:51.251');
INSERT INTO `security_event_log` VALUES (155, 8, 'linhai1', 'TGS_ISSUE_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:55222', NULL, '2026-05-08 05:47:51.718');
INSERT INTO `security_event_log` VALUES (156, 8, 'linhai1', 'GS_AUTH_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:55224', NULL, '2026-05-08 05:47:51.784');
INSERT INTO `security_event_log` VALUES (157, 8, 'linhai1', 'LOGIN_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:57912', NULL, '2026-05-08 05:49:05.119');
INSERT INTO `security_event_log` VALUES (158, 8, 'linhai1', 'TGS_ISSUE_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:57917', NULL, '2026-05-08 05:49:05.496');
INSERT INTO `security_event_log` VALUES (159, 8, 'linhai1', 'GS_AUTH_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:57919', NULL, '2026-05-08 05:49:05.575');
INSERT INTO `security_event_log` VALUES (160, 8, 'linhai1', 'LOGIN_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:49751', NULL, '2026-05-08 05:50:45.731');
INSERT INTO `security_event_log` VALUES (161, 8, 'linhai1', 'TGS_ISSUE_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:49753', NULL, '2026-05-08 05:50:46.089');
INSERT INTO `security_event_log` VALUES (162, 8, 'linhai1', 'GS_AUTH_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:49755', NULL, '2026-05-08 05:50:46.165');
INSERT INTO `security_event_log` VALUES (163, 8, 'linhai1', 'LOGIN_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:56837', NULL, '2026-05-08 05:57:11.724');
INSERT INTO `security_event_log` VALUES (164, 8, 'linhai1', 'TGS_ISSUE_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:56839', NULL, '2026-05-08 05:57:12.072');
INSERT INTO `security_event_log` VALUES (165, 8, 'linhai1', 'GS_AUTH_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:56841', NULL, '2026-05-08 05:57:12.140');
INSERT INTO `security_event_log` VALUES (166, 8, 'linhai1', 'LOGIN_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:53535', NULL, '2026-05-08 05:58:07.067');
INSERT INTO `security_event_log` VALUES (167, 8, 'linhai1', 'TGS_ISSUE_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:53537', NULL, '2026-05-08 05:58:07.450');
INSERT INTO `security_event_log` VALUES (168, 8, 'linhai1', 'GS_AUTH_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:53539', NULL, '2026-05-08 05:58:07.539');
INSERT INTO `security_event_log` VALUES (169, 9, 'linhai2', 'LOGIN_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:53544', NULL, '2026-05-08 05:58:22.043');
INSERT INTO `security_event_log` VALUES (170, 9, 'linhai2', 'TGS_ISSUE_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:53548', NULL, '2026-05-08 05:58:22.477');
INSERT INTO `security_event_log` VALUES (171, 9, 'linhai2', 'GS_AUTH_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:53550', NULL, '2026-05-08 05:58:22.572');
INSERT INTO `security_event_log` VALUES (172, 8, 'linhai1', 'LOGIN_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:61936', NULL, '2026-05-08 06:10:55.170');
INSERT INTO `security_event_log` VALUES (173, 8, 'linhai1', 'TGS_ISSUE_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:61938', NULL, '2026-05-08 06:10:55.537');
INSERT INTO `security_event_log` VALUES (174, 8, 'linhai1', 'GS_AUTH_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:61940', NULL, '2026-05-08 06:10:55.607');
INSERT INTO `security_event_log` VALUES (175, 9, 'linhai2', 'LOGIN_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:61956', NULL, '2026-05-08 06:11:10.432');
INSERT INTO `security_event_log` VALUES (176, 9, 'linhai2', 'TGS_ISSUE_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:61960', NULL, '2026-05-08 06:11:10.882');
INSERT INTO `security_event_log` VALUES (177, 9, 'linhai2', 'GS_AUTH_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:61962', NULL, '2026-05-08 06:11:10.952');
INSERT INTO `security_event_log` VALUES (178, 8, 'linhai1', 'LOGIN_SUCCESS', 1, 'cli_57212097a53f45d5ba0506fd0109d99a', '127.0.0.1:61493', NULL, '2026-05-08 06:12:33.747');
INSERT INTO `security_event_log` VALUES (179, 8, 'linhai1', 'TGS_ISSUE_SUCCESS', 1, 'cli_57212097a53f45d5ba0506fd0109d99a', '127.0.0.1:61495', NULL, '2026-05-08 06:12:34.108');
INSERT INTO `security_event_log` VALUES (180, 8, 'linhai1', 'GS_AUTH_SUCCESS', 1, 'cli_57212097a53f45d5ba0506fd0109d99a', '127.0.0.1:61497', NULL, '2026-05-08 06:12:34.187');
INSERT INTO `security_event_log` VALUES (181, 9, 'linhai2', 'LOGIN_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:49916', NULL, '2026-05-08 06:12:51.351');
INSERT INTO `security_event_log` VALUES (182, 9, 'linhai2', 'TGS_ISSUE_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:49922', NULL, '2026-05-08 06:12:51.775');
INSERT INTO `security_event_log` VALUES (183, 9, 'linhai2', 'GS_AUTH_SUCCESS', 1, 'cli_e3f9b980557249e4ac02af5d4f29c80b', '127.0.0.1:49924', NULL, '2026-05-08 06:12:51.842');
INSERT INTO `security_event_log` VALUES (184, 8, 'linhai1', 'LOGIN_SUCCESS', 1, 'cli_0bb98ac890974313818cb7390693ada2', '127.0.0.1:49994', NULL, '2026-05-08 06:13:43.224');
INSERT INTO `security_event_log` VALUES (185, 8, 'linhai1', 'TGS_ISSUE_SUCCESS', 1, 'cli_0bb98ac890974313818cb7390693ada2', '127.0.0.1:49996', NULL, '2026-05-08 06:13:43.612');
INSERT INTO `security_event_log` VALUES (186, 8, 'linhai1', 'GS_AUTH_SUCCESS', 1, 'cli_0bb98ac890974313818cb7390693ada2', '127.0.0.1:49998', NULL, '2026-05-08 06:13:43.686');
INSERT INTO `security_event_log` VALUES (187, 9, 'linhai2', 'LOGIN_SUCCESS', 1, 'cli_78871739941845af83c64248af091d63', '127.0.0.1:50005', NULL, '2026-05-08 06:14:00.580');
INSERT INTO `security_event_log` VALUES (188, 9, 'linhai2', 'TGS_ISSUE_SUCCESS', 1, 'cli_78871739941845af83c64248af091d63', '127.0.0.1:50009', NULL, '2026-05-08 06:14:01.018');
INSERT INTO `security_event_log` VALUES (189, 9, 'linhai2', 'GS_AUTH_SUCCESS', 1, 'cli_78871739941845af83c64248af091d63', '127.0.0.1:50011', NULL, '2026-05-08 06:14:01.101');
INSERT INTO `security_event_log` VALUES (190, 8, 'linhai1', 'RECONNECT_TIMEOUT', 0, 'Client2', NULL, 'GRACE_PERIOD_EXPIRED', '2026-05-08 06:18:10.045');
INSERT INTO `security_event_log` VALUES (191, 8, 'linhai1', 'LOGIN_SUCCESS', 1, 'cli_2947cebd7db14932b7aa79155309e5c1', '127.0.0.1:62709', NULL, '2026-05-08 06:20:29.297');
INSERT INTO `security_event_log` VALUES (192, 8, 'linhai1', 'TGS_ISSUE_SUCCESS', 1, 'cli_2947cebd7db14932b7aa79155309e5c1', '127.0.0.1:62711', NULL, '2026-05-08 06:20:29.664');
INSERT INTO `security_event_log` VALUES (193, 8, 'linhai1', 'GS_AUTH_SUCCESS', 1, 'cli_2947cebd7db14932b7aa79155309e5c1', '127.0.0.1:62713', NULL, '2026-05-08 06:20:29.733');
INSERT INTO `security_event_log` VALUES (194, 9, 'linhai2', 'LOGIN_SUCCESS', 1, 'cli_c22d8f8fb0674d9fa1e63a97c7cf2813', '127.0.0.1:55859', NULL, '2026-05-08 06:20:41.116');
INSERT INTO `security_event_log` VALUES (195, 9, 'linhai2', 'TGS_ISSUE_SUCCESS', 1, 'cli_c22d8f8fb0674d9fa1e63a97c7cf2813', '127.0.0.1:55863', NULL, '2026-05-08 06:20:41.528');
INSERT INTO `security_event_log` VALUES (196, 9, 'linhai2', 'GS_AUTH_SUCCESS', 1, 'cli_c22d8f8fb0674d9fa1e63a97c7cf2813', '127.0.0.1:55865', NULL, '2026-05-08 06:20:41.597');
INSERT INTO `security_event_log` VALUES (197, 8, 'linhai1', 'LOGIN_SUCCESS', 1, 'cli_42b48e5180634654b56ffd0dac79caca', '127.0.0.1:63922', NULL, '2026-05-08 12:12:48.180');
INSERT INTO `security_event_log` VALUES (198, 8, 'linhai1', 'TGS_ISSUE_SUCCESS', 1, 'cli_42b48e5180634654b56ffd0dac79caca', '127.0.0.1:60242', NULL, '2026-05-08 12:12:48.564');
INSERT INTO `security_event_log` VALUES (199, 8, 'linhai1', 'GS_AUTH_SUCCESS', 1, 'cli_42b48e5180634654b56ffd0dac79caca', '127.0.0.1:60244', NULL, '2026-05-08 12:12:48.637');
INSERT INTO `security_event_log` VALUES (200, 9, 'linhai2', 'LOGIN_SUCCESS', 1, 'cli_0f4673f98b704cfeb0f11170980c04c0', '127.0.0.1:62837', NULL, '2026-05-08 12:13:03.355');
INSERT INTO `security_event_log` VALUES (201, 9, 'linhai2', 'TGS_ISSUE_SUCCESS', 1, 'cli_0f4673f98b704cfeb0f11170980c04c0', '127.0.0.1:62844', NULL, '2026-05-08 12:13:03.808');
INSERT INTO `security_event_log` VALUES (202, 9, 'linhai2', 'GS_AUTH_SUCCESS', 1, 'cli_0f4673f98b704cfeb0f11170980c04c0', '127.0.0.1:62846', NULL, '2026-05-08 12:13:03.880');
INSERT INTO `security_event_log` VALUES (203, 8, 'linhai1', 'LOGIN_SUCCESS', 1, 'cli_320728da48d54924835d75de6ff9d726', '127.0.0.1:50467', NULL, '2026-05-08 12:19:32.881');
INSERT INTO `security_event_log` VALUES (204, 8, 'linhai1', 'TGS_ISSUE_SUCCESS', 1, 'cli_320728da48d54924835d75de6ff9d726', '127.0.0.1:50471', NULL, '2026-05-08 12:19:33.270');
INSERT INTO `security_event_log` VALUES (205, 9, 'linhai2', 'RECONNECT_TIMEOUT', 0, 'Client2', NULL, 'GRACE_PERIOD_EXPIRED', '2026-05-08 12:19:33.364');
INSERT INTO `security_event_log` VALUES (206, 8, 'linhai1', 'RECONNECT_TIMEOUT', 0, 'Client1', NULL, 'GRACE_PERIOD_EXPIRED', '2026-05-08 12:19:33.379');
INSERT INTO `security_event_log` VALUES (207, 8, 'linhai1', 'GS_AUTH_SUCCESS', 1, 'cli_320728da48d54924835d75de6ff9d726', '127.0.0.1:50473', NULL, '2026-05-08 12:19:33.383');
INSERT INTO `security_event_log` VALUES (208, 9, 'linhai2', 'LOGIN_SUCCESS', 1, 'cli_c3b8d803f1f14d1484ed78447c241282', '127.0.0.1:57072', NULL, '2026-05-08 12:19:48.782');
INSERT INTO `security_event_log` VALUES (209, 9, 'linhai2', 'TGS_ISSUE_SUCCESS', 1, 'cli_c3b8d803f1f14d1484ed78447c241282', '127.0.0.1:57077', NULL, '2026-05-08 12:19:49.249');
INSERT INTO `security_event_log` VALUES (210, 9, 'linhai2', 'GS_AUTH_SUCCESS', 1, 'cli_c3b8d803f1f14d1484ed78447c241282', '127.0.0.1:53918', NULL, '2026-05-08 12:19:49.322');
INSERT INTO `security_event_log` VALUES (211, 10, 'linhai3', 'REGISTER', 1, 'cli_e3d2db9f2b964621a087828a4f345e1d', '127.0.0.1:58427', NULL, '2026-05-08 12:24:24.924');
INSERT INTO `security_event_log` VALUES (212, 10, 'linhai3', 'LOGIN_SUCCESS', 1, 'cli_e3d2db9f2b964621a087828a4f345e1d', '127.0.0.1:52444', NULL, '2026-05-08 12:24:51.712');
INSERT INTO `security_event_log` VALUES (213, 10, 'linhai3', 'TGS_ISSUE_SUCCESS', 1, 'cli_e3d2db9f2b964621a087828a4f345e1d', '127.0.0.1:52447', NULL, '2026-05-08 12:24:52.103');
INSERT INTO `security_event_log` VALUES (214, 9, 'linhai2', 'RECONNECT_TIMEOUT', 0, 'Client2', NULL, 'GRACE_PERIOD_EXPIRED', '2026-05-08 12:24:52.172');
INSERT INTO `security_event_log` VALUES (215, 8, 'linhai1', 'RECONNECT_TIMEOUT', 0, 'Client1', NULL, 'GRACE_PERIOD_EXPIRED', '2026-05-08 12:24:52.202');
INSERT INTO `security_event_log` VALUES (216, 10, 'linhai3', 'GS_AUTH_SUCCESS', 1, 'cli_e3d2db9f2b964621a087828a4f345e1d', '127.0.0.1:52449', NULL, '2026-05-08 12:24:52.205');
INSERT INTO `security_event_log` VALUES (217, 8, 'linhai1', 'LOGIN_SUCCESS', 1, 'cli_6fb53766656441b9ac0c332fddcfe812', '127.0.0.1:52519', NULL, '2026-05-08 12:25:15.420');
INSERT INTO `security_event_log` VALUES (218, 8, 'linhai1', 'TGS_ISSUE_SUCCESS', 1, 'cli_6fb53766656441b9ac0c332fddcfe812', '127.0.0.1:52524', NULL, '2026-05-08 12:25:15.894');
INSERT INTO `security_event_log` VALUES (219, 8, 'linhai1', 'GS_AUTH_SUCCESS', 1, 'cli_6fb53766656441b9ac0c332fddcfe812', '127.0.0.1:52526', NULL, '2026-05-08 12:25:15.987');
INSERT INTO `security_event_log` VALUES (220, 9, 'linhai2', 'LOGIN_SUCCESS', 1, 'cli_2f7b307da2044433b6f362a8cd514c38', '127.0.0.1:54271', NULL, '2026-05-08 13:56:34.147');
INSERT INTO `security_event_log` VALUES (221, 9, 'linhai2', 'TGS_ISSUE_SUCCESS', 1, 'cli_2f7b307da2044433b6f362a8cd514c38', '127.0.0.1:54276', NULL, '2026-05-08 13:56:34.586');
INSERT INTO `security_event_log` VALUES (222, 10, 'linhai3', 'RECONNECT_TIMEOUT', 0, 'Client1', NULL, 'GRACE_PERIOD_EXPIRED', '2026-05-08 13:56:34.666');
INSERT INTO `security_event_log` VALUES (223, 8, 'linhai1', 'RECONNECT_TIMEOUT', 0, 'Client2', NULL, 'GRACE_PERIOD_EXPIRED', '2026-05-08 13:56:34.670');
INSERT INTO `security_event_log` VALUES (224, 9, 'linhai2', 'GS_AUTH_SUCCESS', 1, 'cli_2f7b307da2044433b6f362a8cd514c38', '127.0.0.1:54278', NULL, '2026-05-08 13:56:34.673');
INSERT INTO `security_event_log` VALUES (225, 8, 'linhai1', 'LOGIN_SUCCESS', 1, 'cli_7582e3bec098454a8ab76d233c0193ae', '127.0.0.1:54334', NULL, '2026-05-08 13:56:47.337');
INSERT INTO `security_event_log` VALUES (226, 8, 'linhai1', 'TGS_ISSUE_SUCCESS', 1, 'cli_7582e3bec098454a8ab76d233c0193ae', '127.0.0.1:54338', NULL, '2026-05-08 13:56:47.776');
INSERT INTO `security_event_log` VALUES (227, 8, 'linhai1', 'GS_AUTH_SUCCESS', 1, 'cli_7582e3bec098454a8ab76d233c0193ae', '127.0.0.1:54340', NULL, '2026-05-08 13:56:47.848');

-- ----------------------------
-- Table structure for user_account
-- ----------------------------
DROP TABLE IF EXISTS `user_account`;
CREATE TABLE `user_account`  (
  `user_id` bigint(20) UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '用户唯一 ID，写入 TGT 和后续 ServiceTicket',
  `username` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '用户登录名；AS 写入前统一 trim + lower',
  `password_hash` varbinary(64) NOT NULL COMMENT 'PBKDF2-HMAC-SHA256 后的密码摘要，不保存明文密码',
  `password_salt` varbinary(32) NOT NULL COMMENT 'PBKDF2 salt，当前实现默认生成 16 字节',
  `pbkdf2_iter` int(10) UNSIGNED NOT NULL DEFAULT 100000 COMMENT 'PBKDF2 迭代次数',
  `login_gen` int(10) UNSIGNED NOT NULL DEFAULT 0 COMMENT '登录代数；成功登录和改密时递增，用于让旧票据/旧会话失效',
  `status` tinyint(3) UNSIGNED NOT NULL DEFAULT 1 COMMENT '账号状态：1 表示启用，0 表示禁用',
  `last_login_at` datetime(3) NULL DEFAULT NULL COMMENT '最近一次成功登录时间',
  `created_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '账号创建时间',
  `updated_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '账号更新时间',
  PRIMARY KEY (`user_id`) USING BTREE,
  UNIQUE INDEX `uk_user_account_username`(`username`) USING BTREE,
  INDEX `idx_user_account_status`(`status`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 11 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = 'AS 用户账号表' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of user_account
-- ----------------------------
INSERT INTO `user_account` VALUES (1, 'tgs_smoke_6b21af42bc', 0x8B63E36FC6023F1DAC41E379447220966BD36DD64AB3478E1EDE1D800A1A7053, 0xE59847C55F3D487B766C7F0B33F04675, 100000, 0, 1, NULL, '2026-05-07 22:48:31.451', '2026-05-07 22:48:31.451');
INSERT INTO `user_account` VALUES (2, 'tgs_smoke_9cb1590d51', 0xC4272133194468AC9F981FFB942FB0CEF30545893BC7283F76436C3AC0C24335, 0x836BCBB657E9BDEDDA619E4A5090201B, 100000, 0, 1, NULL, '2026-05-07 22:51:44.412', '2026-05-07 22:51:44.412');
INSERT INTO `user_account` VALUES (3, 'tgs_smoke_03a517c139', 0x1CEC2FF6E68F1940ADB84718497890E7B15523CF6DC99BF78134C4134A44237C, 0xD55ED232CC1E9848FF75F35BE4A9A98F, 100000, 0, 1, NULL, '2026-05-07 22:55:28.070', '2026-05-07 22:55:28.070');
INSERT INTO `user_account` VALUES (4, 'tgs_smoke_60a807bac6', 0x7C1DBA3B886C63F36844D6072D12417C9A35301D1B35255A9835D41D0CC2F2BF, 0x7F5F6E1D287967E02306F99FE7135433, 100000, 1, 1, '2026-05-07 15:00:49.075', '2026-05-07 23:00:48.994', '2026-05-07 23:00:49.075');
INSERT INTO `user_account` VALUES (5, 'tgs_smoke_ad34582274', 0x0BE03210A4FAFC33922AA9B22D9062971139B505A418616A5EC6EFC83F4E1802, 0x9CF3CFC51F1169E3B6DEB9E8E8B0CDA8, 100000, 1, 1, '2026-05-07 15:05:35.449', '2026-05-07 23:05:35.356', '2026-05-07 23:05:35.449');
INSERT INTO `user_account` VALUES (6, 'testuser', 0x47A4241B2B3352FE4B5351784EF36DF0D7A234F2B8814E15950D32FFDFF2E4F6, 0x7C69321BB12978E916C72165B4EBB436, 100000, 4, 1, '2026-05-07 15:55:09.791', '2026-05-07 23:38:54.060', '2026-05-07 23:55:09.791');
INSERT INTO `user_account` VALUES (7, 'testuser1', 0x164F0C1ABF50C419E311FB26C8AB971928092B412B7C9A1360740ACA49847420, 0x3E5C9B6DEDF09B11B60E8448A3D4FC60, 100000, 1, 1, '2026-05-07 18:24:05.828', '2026-05-08 02:24:02.275', '2026-05-08 02:24:05.828');
INSERT INTO `user_account` VALUES (8, 'linhai1', 0x7875E5BA7BCBF645826AA4AA6C580303D889D8FA54C8BE407CA36323011B8D7D, 0x8B551B8657BC372F804F06C227002453, 100000, 45, 1, '2026-05-08 05:56:47.297', '2026-05-08 02:36:48.311', '2026-05-08 13:56:47.298');
INSERT INTO `user_account` VALUES (9, 'linhai2', 0x7831D84C7CAB32D4CFC5AC1EADF1547DE5BF8E1FFDA789B4F1B19FC7C67C4224, 0x3896F14540303F96155306C0EAAC164D, 100000, 17, 1, '2026-05-08 05:56:34.102', '2026-05-08 02:37:38.125', '2026-05-08 13:56:34.102');
INSERT INTO `user_account` VALUES (10, 'linhai3', 0xA95C59344DC4E638EAB951822D504844DDB7ED5EC6AEB29C639FA77553AEF081, 0x847791FDF15DEC9E82A29E6A351BDBA2, 100000, 1, 1, '2026-05-08 04:24:51.665', '2026-05-08 12:24:24.923', '2026-05-08 12:24:51.665');

SET FOREIGN_KEY_CHECKS = 1;
