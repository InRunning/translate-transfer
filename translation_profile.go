package main

// TranslationProfile describes the target language and prompts used by a
// translation endpoint.
type TranslationProfile struct {
	Name           string
	TargetLanguage string
	SentencePrompt string
	WordPrompt     string
}

var chineseTranslationProfile = TranslationProfile{
	Name:           "中文",
	TargetLanguage: "zh-CN",
	SentencePrompt: "你是一个智能翻译助手，下面是句子，请给出该句子的释义。示例：输入：I want to go home 输出: 我想回家 ./no_think",
	WordPrompt:     "你是一个智能翻译助手，下面是单词，你需要给出该单词最常用的一个释义，并给出美式音标和英式音标，示例：输入：example 输出格式: 例子\n 美式音标：/ɪɡˈzæmpəl/ \n英式音标：/ɪɡˈzɑːmpəl/ ./no_think",
}

var tagalogTranslationProfile = TranslationProfile{
	Name:           "Tagalog",
	TargetLanguage: "tl",
	SentencePrompt: "你是一个智能翻译助手。将下面的英文句子翻译成自然、常用的 Tagalog（Filipino）。仅输出译文，不要解释、不要输出思考过程。示例：输入：I want to go home 输出：Gusto kong umuwi. ./no_think",
	WordPrompt:     "你是一个智能翻译助手。将下面的英文单词翻译为最常用的一个 Tagalog（Filipino）释义，并给出美式音标和英式音标。严格按以下格式输出：\nTagalog：<最常用释义>\nAmerican IPA：/<IPA>/\nBritish  IPA：/<IPA>/\n不要添加解释或思考过程。 ./no_think",
}

func (p TranslationProfile) prompt(isWordInput bool) string {
	if isWordInput {
		return p.WordPrompt
	}
	return p.SentencePrompt
}
