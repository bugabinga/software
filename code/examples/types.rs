//! Example code the book quotes from. Type-checked by `make check-code`, so a
//! listing that stops compiling breaks the build instead of the reader.

// [newtype]
/// A width in characters, not to be confused with a width in pixels.
pub struct Columns(pub u16);

pub fn wrap(text: &str, width: Columns) -> Vec<&str> {
    let Columns(width) = width;
    text.split_whitespace().take(width as usize).collect()
}
// [/newtype]

// [phantom]
use std::marker::PhantomData;

pub struct Checked;
pub struct Raw;

/// A path that remembers whether anyone has validated it.
pub struct Path<State> {
    inner: String,
    _state: PhantomData<State>,
}

impl Path<Raw> {
    pub fn new(inner: String) -> Self {
        Path { inner, _state: PhantomData }
    }

    pub fn check(self) -> Option<Path<Checked>> {
        if self.inner.starts_with('/') {
            Some(Path { inner: self.inner, _state: PhantomData })
        } else {
            None
        }
    }
}

impl Path<Checked> {
    pub fn as_str(&self) -> &str {
        &self.inner
    }
}
// [/phantom]
