package main

import "testing"

func TestNormalizeWordTextCutsBulletSuffix(t *testing.T) {
	input := "pictures  • 新郎/新娘的伴郎伴娘团摆姿势拍照"

	if got := normalizeWordText(input); got != "pictures" {
		t.Fatalf("normalizeWordText() = %q, want %q", got, "pictures")
	}
}

func TestIsWordCutsBulletSuffix(t *testing.T) {
	input := "pictures  • 新郎/新娘的伴郎伴娘团摆姿势拍照"

	if !isWord(input) {
		t.Fatalf("isWord() = false, want true")
	}
}
