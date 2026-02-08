#!/usr/bin/env python3
"""
语音识别测试
使用 faster-whisper 将音频转换为文字
"""

import os
import sys

def test_whisper():
    """测试faster-whisper"""
    print("=" * 60)
    print("🎤 Faster-Whisper 语音识别测试")
    print("=" * 60)
    
    try:
        from faster_whisper import WhisperModel
        
        print("\n📦 加载模型...")
        # 使用 tiny 模型 (最快) 或 base (平衡)
        model = WhisperModel("tiny", compute_type="int8")
        print("✅ 模型加载成功!")
        
        print("\n📝 说明:")
        print("   1. 当前测试模式: 无音频文件")
        print("   2. 实际使用时，会监听麦克风输入")
        print("   3. 将音频转换为文字后执行任务")
        
        print("\n✅ faster-whisper 已就绪!")
        print("\n🎯 下一步:")
        print("   - 需要配置麦克风监听")
        print("   - 或者接收音频文件进行识别")
        
        return True
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        return False

def transcribe_audio(audio_path: str):
    """转录音频文件"""
    print(f"\n📂 转录音频: {audio_path}")
    
    if not os.path.exists(audio_path):
        print(f"❌ 文件不存在: {audio_path}")
        return None
    
    try:
        from faster_whisper import WhisperModel
        
        model = WhisperModel("tiny", compute_type="int8")
        
        print("🔄 转录中...")
        segments, info = model.transcribe(audio_path, beam_size=5)
        
        print(f"📊 语言: {info.language} (概率: {info.language_probability:.2f})")
        
        text = ""
        for segment in segments:
            print(f"  [{segment.start:.2f}s - {segment.end:.2f}s] {segment.text}")
            text += segment.text
        
        return text.strip()
        
    except Exception as e:
        print(f"❌ 转录失败: {e}")
        return None

if __name__ == "__main__":
    # 测试加载
    test_whisper()
    
    # 如果有音频文件参数
    if len(sys.argv) > 1:
        transcribe_audio(sys.argv[1])
