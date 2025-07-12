#!/usr/bin/env python3
import os
import sys
import time
import requests
import subprocess
import threading
from supervisor import childutils

# 配置常量
MAX_FAILURES = 3
HEALTH_CHECK_TIMEOUT = 3  # 减少超时时间
RESTART_COOLDOWN = 60

class SimpleHealthChecker:
    """简单的健康检查器"""
    
    def __init__(self):
        self.failure_count = 0
        self.last_restart_time = 0
        self.is_checking = False  # 添加检查状态标记
        self.is_restarting = False  # 添加重启状态标记
        
        # 配置 web-service 的健康检查 URL
        host = os.getenv('HOST', '0.0.0.0')
        port = os.getenv('PORT', '9001')
        self.health_url = f'http://{host}:{port}/inference_pipelines/list'
    
    def check_web_service(self) -> bool:
        """检查 web-service 的健康状态"""
        try:
            response = requests.get(
                self.health_url, 
                timeout=HEALTH_CHECK_TIMEOUT,
                headers={'Connection': 'close'}  # 避免连接复用问题
            )
            return response.status_code == 200
        except Exception as e:
            print(f"Web service health check failed: {e}")
            return False
    
    def should_restart(self) -> bool:
        """判断是否需要重启服务"""
        current_time = time.time()
        
        # 检查是否在冷却期内
        if current_time - self.last_restart_time < RESTART_COOLDOWN:
            return False
            
        # 检查失败次数
        if self.failure_count >= MAX_FAILURES:
            print(f"Web service failed {self.failure_count} times, triggering restart")
            self.last_restart_time = current_time
            self.failure_count = 0
            return True
            
        return False
    
    def handle_health_check(self):
        """处理健康检查逻辑"""
        # 如果正在检查或重启，跳过此次检查
        if self.is_checking or self.is_restarting:
            print("Health check already in progress, skipping...")
            return
            
        self.is_checking = True
        try:
            is_healthy = self.check_web_service()
            
            if is_healthy:
                if self.failure_count > 0:
                    print("Web service recovered")
                    self.failure_count = 0
            else:
                self.failure_count += 1
                print(f"Web service unhealthy ({self.failure_count}/{MAX_FAILURES})")
                
                if self.should_restart():
                    # 使用线程异步重启，避免阻塞事件处理
                    restart_thread = threading.Thread(target=self.restart_services)
                    restart_thread.daemon = True
                    restart_thread.start()
        finally:
            self.is_checking = False
    
    def restart_services(self):
        """重启 start-service 和 web-service"""
        if self.is_restarting:
            print("Services are already being restarted, skipping...")
            return
            
        self.is_restarting = True
        services_to_restart = ['start-service', 'web-service']
        
        try:
            for service_name in services_to_restart:
                try:
                    result = subprocess.run(
                        ['supervisorctl', 'restart', service_name], 
                        check=True, 
                        timeout=15,  # 减少超时时间
                        capture_output=True, 
                        text=True
                    )
                    print(f"Successfully restarted {service_name}")
                except subprocess.TimeoutExpired:
                    print(f"Timeout restarting {service_name}")
                except subprocess.CalledProcessError as e:
                    print(f"Failed to restart {service_name}: {e.stderr}")
                except Exception as e:
                    print(f"Error restarting {service_name}: {e}")
                
                # 在重启服务之间添加短暂延迟
                time.sleep(1)  # 减少延迟时间
        finally:
            self.is_restarting = False

def main():
    """主函数"""
    health_checker = SimpleHealthChecker()
    print("Simple health check monitor started")
    
    while True:
        try:
            # 等待 supervisor 事件
            headers, payload = childutils.listener.wait(sys.stdin, sys.stdout)
            
            # 检查是否是 TICK 事件
            if headers['eventname'] == 'TICK_60':
                # 使用线程异步处理健康检查，避免阻塞事件循环
                check_thread = threading.Thread(target=health_checker.handle_health_check)
                check_thread.daemon = True
                check_thread.start()
            
            # 立即确认事件处理完成，避免缓冲区溢出
            childutils.listener.ok(sys.stdout)
            
        except KeyboardInterrupt:
            print("Health check monitor stopped")
            break
        except Exception as e:
            print(f"Error in main loop: {e}")
            try:
                childutils.listener.ok(sys.stdout)
            except:
                pass

if __name__ == '__main__':
    main()